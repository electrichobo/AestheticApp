//! Multi-Camera Setup Matching & Cross-Angle Continuity Engine
//!
//! Analyzes shot setups across scenes or episode folders, evaluates pairwise
//! exposure, white balance, and lighting continuity, and synthesizes
//! American Society of Cinematographers Color Decision Lists (ASC CDL) and
//! 3D LUTs (.cube) to automatically match coverage angles to the Hero Master.

use aesthetic_models::multicam::{AscCdlCorrection, CrossAngleMatchReport, PairwiseSetupDelta};
use aesthetic_models::window::ShotTake;

/// Evaluates multi-camera setup continuity across a collection of candidate takes
/// and synthesizes ASC CDL grading corrections relative to the Hero Master.
pub fn compute_cross_angle_setup_matching(
    group_name: &str,
    takes: &[ShotTake],
) -> CrossAngleMatchReport {
    if takes.is_empty() {
        return CrossAngleMatchReport {
            group_name: group_name.to_string(),
            ..Default::default()
        };
    }

    // Designate the highest-scoring candidate as the Hero Master Reference
    let master = takes.first().unwrap();
    let master_id = master.take_id.clone();
    let master_exp = &master.measured.exposure;
    let master_col = &master.measured.color;
    let master_opt = &master.measured.optics;
    let master_craft = master.craft.as_ref();

    let master_luma = master_exp.histogram_mean.max(1.0);
    let master_kelvin = master_col.estimated_kelvin.max(1000.0);
    let master_kf = master_craft.map(|c| c.lighting.key_to_fill_ratio).unwrap_or(2.5);
    let master_sharp = master_opt.sharpness_laplacian.max(0.1);

    let mut pairwise_matches = Vec::new();
    let mut total_delta_e = 0.0;
    let mut max_exp_delta: f32 = 0.0;
    let mut max_kelvin_delta: f32 = 0.0;

    for (idx, take) in takes.iter().enumerate() {
        if idx == 0 {
            // Master matches itself with a clean neutral identity
            pairwise_matches.push(PairwiseSetupDelta {
                source_take_id: take.take_id.clone(),
                target_take_id: master_id.clone(),
                exposure_stops_delta: 0.0,
                kelvin_delta: 0.0,
                color_delta_e: 0.0,
                key_to_fill_ratio_delta: 0.0,
                sharpness_ratio: 1.0,
                match_status: "Hero Reference Master".to_string(),
                recommended_cdl: AscCdlCorrection {
                    summary_guidance: "Designated Hero Master: Baseline grade anchor for sequence".to_string(),
                    ..Default::default()
                },
            });
            continue;
        }

        let take_exp = &take.measured.exposure;
        let take_col = &take.measured.color;
        let take_opt = &take.measured.optics;
        let take_craft = take.craft.as_ref();

        let take_luma = take_exp.histogram_mean.max(1.0);
        let take_kelvin = take_col.estimated_kelvin.max(1000.0);
        let take_kf = take_craft.map(|c| c.lighting.key_to_fill_ratio).unwrap_or(2.5);
        let take_sharp = take_opt.sharpness_laplacian.max(0.1);

        // 1. Exposure Delta in EV stops (log2 luminance ratio)
        let exp_stops_delta = (take_luma / master_luma).log2();
        max_exp_delta = max_exp_delta.max(exp_stops_delta.abs());

        // 2. White Balance Kelvin Delta (positive = source is warmer than master)
        let kelvin_delta = take_kelvin - master_kelvin;
        max_kelvin_delta = max_kelvin_delta.max(kelvin_delta.abs());

        // 3. Perceptual Color Delta approximation from D65 deviation, Kelvin shift, and saturation
        let d_d65 = (take_col.delta_e_d65 - master_col.delta_e_d65).abs();
        let d_sat = (take_col.saturation_mean - master_col.saturation_mean).abs() * 8.0;
        let d_k = (kelvin_delta / 180.0).abs();
        let color_delta_e = (d_d65 + d_sat + d_k).clamp(0.0, 50.0);
        total_delta_e += color_delta_e;

        // 4. Lighting & Optics
        let kf_delta = take_kf - master_kf;
        let sharpness_ratio = take_sharp / master_sharp;

        // 5. Categorical Match Status
        let match_status = if color_delta_e < 1.8 && exp_stops_delta.abs() < 0.35 {
            "Matched (< 1.8 ΔE)".to_string()
        } else if color_delta_e < 3.5 && exp_stops_delta.abs() < 0.75 {
            "Minor Trim Needed (1.8–3.5 ΔE)".to_string()
        } else {
            "Grading Correction Advised (> 3.5 ΔE)".to_string()
        };

        // 6. Synthesize ASC CDL Color Correction
        let cdl = synthesize_asc_cdl(
            exp_stops_delta,
            kelvin_delta,
            take_exp,
            master_exp,
            take_col,
            master_col,
        );

        pairwise_matches.push(PairwiseSetupDelta {
            source_take_id: take.take_id.clone(),
            target_take_id: master_id.clone(),
            exposure_stops_delta: (exp_stops_delta * 100.0).round() / 100.0,
            kelvin_delta: kelvin_delta.round(),
            color_delta_e: (color_delta_e * 10.0).round() / 10.0,
            key_to_fill_ratio_delta: (kf_delta * 100.0).round() / 100.0,
            sharpness_ratio: (sharpness_ratio * 100.0).round() / 100.0,
            match_status,
            recommended_cdl: cdl,
        });
    }

    let avg_delta_e = if takes.len() > 1 {
        total_delta_e / ((takes.len() - 1) as f32)
    } else {
        0.0
    };

    // Overall Multi-Camera Consistency Score (100 - penalties for ΔE, stops, and Kelvin drift)
    let consistency_penalty = (avg_delta_e * 7.5) + (max_exp_delta * 18.0) + (max_kelvin_delta / 85.0);
    let overall_consistency_score = (100.0 - consistency_penalty).clamp(10.0, 100.0);

    CrossAngleMatchReport {
        group_name: group_name.to_string(),
        hero_master_take_id: master_id,
        total_takes: takes.len(),
        average_scene_delta_e: (avg_delta_e * 10.0).round() / 10.0,
        max_exposure_stops_delta: (max_exp_delta * 100.0).round() / 100.0,
        max_kelvin_delta: max_kelvin_delta.round(),
        overall_consistency_score: (overall_consistency_score * 10.0).round() / 10.0,
        pairwise_matches,
    }
}

/// Derives ASC CDL (Slope, Offset, Power, Saturation) mathematically from exposure and chromaticity deltas.
fn synthesize_asc_cdl(
    exp_stops_delta: f32,
    kelvin_delta: f32,
    source_exp: &aesthetic_models::physics::ExposurePhysics,
    master_exp: &aesthetic_models::physics::ExposurePhysics,
    source_col: &aesthetic_models::physics::ColorPhysics,
    master_col: &aesthetic_models::physics::ColorPhysics,
) -> AscCdlCorrection {
    // 1. Base Exposure Gain (Slope) to match target master:
    // If source is underexposed (-0.5 stops), gain multiplier is 2^(+0.5) = 1.41
    let exp_gain = 2.0f32.powf(-exp_stops_delta).clamp(0.4, 2.5);

    // 2. Color Temperature White Balance Trims:
    // If source is warmer than master (kelvin_delta > 0), cool down: reduce red, boost blue
    // If source is cooler than master (kelvin_delta < 0), warm up: boost red, reduce blue
    let kelvin_factor = (kelvin_delta / 18000.0).clamp(-0.25, 0.25);
    let slope_r = (exp_gain * (1.0 - kelvin_factor)).clamp(0.2, 3.0);
    let slope_g = exp_gain.clamp(0.2, 3.0);
    let slope_b = (exp_gain * (1.0 + kelvin_factor)).clamp(0.2, 3.0);

    // 3. Shadow Lift (Offset):
    // Align shadow baseline between source and master
    let shadow_diff = (master_exp.el_zones.zone_0_black_pct - source_exp.el_zones.zone_0_black_pct) * 0.003;
    let offset_val = shadow_diff.clamp(-0.15, 0.15);
    let offset_r = offset_val;
    let offset_g = offset_val;
    let offset_b = offset_val;

    // 4. Midtone Gamma (Power):
    // If source has lower dynamic range / steeper midtone contrast, adjust power curve
    let contrast_ratio = (source_exp.dynamic_range_stops / master_exp.dynamic_range_stops.max(0.1)).clamp(0.5, 2.0);
    let power_val = (1.0 / contrast_ratio.sqrt()).clamp(0.7, 1.4);
    let power_r = power_val;
    let power_g = power_val;
    let power_b = power_val;

    // 5. Saturation:
    // Ratio of master chroma to source chroma
    let master_chroma = (master_col.saturation_mean * 100.0).max(1.0);
    let source_chroma = (source_col.saturation_mean * 100.0).max(1.0);
    let saturation = (master_chroma / source_chroma).clamp(0.6, 1.6);

    // 6. Natural Language Grading Guidance Summary
    let mut guidance = Vec::new();
    if exp_stops_delta.abs() > 0.15 {
        if exp_stops_delta < 0.0 {
            guidance.push(format!("Boost exposure by +{:.2} EV", exp_stops_delta.abs()));
        } else {
            guidance.push(format!("Pull exposure down by -{:.2} EV", exp_stops_delta));
        }
    }
    if kelvin_delta.abs() > 120.0 {
        if kelvin_delta > 0.0 {
            guidance.push(format!("Cool white balance by -{}K (source is warm)", kelvin_delta.round()));
        } else {
            guidance.push(format!("Warm white balance by +{}K (source is cool)", kelvin_delta.abs().round()));
        }
    }
    if offset_val.abs() > 0.015 {
        if offset_val > 0.0 {
            guidance.push("Lift shadow pedestal".to_string());
        } else {
            guidance.push("Crush deep blacks".to_string());
        }
    }
    if (saturation - 1.0).abs() > 0.08 {
        if saturation > 1.0 {
            guidance.push(format!("Boost saturation +{:.0}%", (saturation - 1.0) * 100.0));
        } else {
            guidance.push(format!("Reduce saturation -{:.0}%", (1.0 - saturation) * 100.0));
        }
    }
    if guidance.is_empty() {
        guidance.push("Close match: Minor trim only".to_string());
    }

    AscCdlCorrection {
        slope: [
            (slope_r * 1000.0).round() / 1000.0,
            (slope_g * 1000.0).round() / 1000.0,
            (slope_b * 1000.0).round() / 1000.0,
        ],
        offset: [
            (offset_r * 1000.0).round() / 1000.0,
            (offset_g * 1000.0).round() / 1000.0,
            (offset_b * 1000.0).round() / 1000.0,
        ],
        power: [
            (power_r * 1000.0).round() / 1000.0,
            (power_g * 1000.0).round() / 1000.0,
            (power_b * 1000.0).round() / 1000.0,
        ],
        saturation: (saturation * 1000.0).round() / 1000.0,
        summary_guidance: guidance.join(", "),
    }
}

/// Generates an industry-standard ASC CDL XML file content matching DaVinci Resolve & Premiere Pro specs.
pub fn generate_asc_cdl_xml(
    correction: &AscCdlCorrection,
    source_id: &str,
    target_id: &str,
) -> String {
    format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<ColorDecisionList xmlns="urn:ASC:CDL:v1.01">
  <ColorDecision>
    <ColorCorrection id="{source_id}_to_{target_id}">
      <SOPNode>
        <Description>AESTHETIC Multi-Cam Match: {source_id} aligned to {target_id}</Description>
        <Slope>{:.6} {:.6} {:.6}</Slope>
        <Offset>{:.6} {:.6} {:.6}</Offset>
        <Power>{:.6} {:.6} {:.6}</Power>
      </SOPNode>
      <SatNode>
        <Saturation>{:.6}</Saturation>
      </SatNode>
    </ColorCorrection>
  </ColorDecision>
</ColorDecisionList>
"#,
        correction.slope[0],
        correction.slope[1],
        correction.slope[2],
        correction.offset[0],
        correction.offset[1],
        correction.offset[2],
        correction.power[0],
        correction.power[1],
        correction.power[2],
        correction.saturation,
    )
}

/// Generates a standard Adobe / DaVinci Resolve 3D LUT (.cube) file representing the ASC CDL correction.
pub fn generate_3d_lut_cube(
    correction: &AscCdlCorrection,
    title: &str,
    size: usize,
) -> String {
    let lut_size = size.clamp(9, 33);
    let mut out = String::new();
    out.push_str("# Generated by AESTHETIC Cinematography Intelligence Engine\n");
    out.push_str(&format!("TITLE \"{}\"\n", title));
    out.push_str(&format!("LUT_3D_SIZE {}\n", lut_size));
    out.push_str("DOMAIN_MIN 0.0 0.0 0.0\n");
    out.push_str("DOMAIN_MAX 1.0 1.0 1.0\n\n");

    let step = 1.0 / ((lut_size - 1) as f32);

    for b_idx in 0..lut_size {
        let b_in = (b_idx as f32) * step;
        for g_idx in 0..lut_size {
            let g_in = (g_idx as f32) * step;
            for r_idx in 0..lut_size {
                let r_in = (r_idx as f32) * step;

                // 1. ASC CDL SOP (Slope, Offset, Power)
                let r_sop = ((r_in * correction.slope[0] + correction.offset[0]).max(0.0)).powf(correction.power[0]);
                let g_sop = ((g_in * correction.slope[1] + correction.offset[1]).max(0.0)).powf(correction.power[1]);
                let b_sop = ((b_in * correction.slope[2] + correction.offset[2]).max(0.0)).powf(correction.power[2]);

                // 2. Saturation
                let luma = 0.2126 * r_sop + 0.7152 * g_sop + 0.0722 * b_sop;
                let r_out = (luma + correction.saturation * (r_sop - luma)).clamp(0.0, 1.0);
                let g_out = (luma + correction.saturation * (g_sop - luma)).clamp(0.0, 1.0);
                let b_out = (luma + correction.saturation * (b_sop - luma)).clamp(0.0, 1.0);

                out.push_str(&format!("{:.6} {:.6} {:.6}\n", r_out, g_out, b_out));
            }
        }
    }

    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use aesthetic_models::physics::{ColorPhysics, ExposurePhysics};
    use aesthetic_models::window::ShotTake;

    #[test]
    fn test_multicam_matching_and_cdl_generation() {
        let mut take1 = ShotTake {
            take_id: "take_001".to_string(),
            ..Default::default()
        };
        take1.measured.exposure = ExposurePhysics {
            histogram_mean: 120.0,
            dynamic_range_stops: 10.5,
            ..Default::default()
        };
        take1.measured.exposure.el_zones.zone_0_black_pct = 1.5;
        take1.measured.color = ColorPhysics {
            estimated_kelvin: 5600.0,
            saturation_mean: 0.35,
            delta_e_d65: 2.1,
            ..Default::default()
        };

        let mut take2 = ShotTake {
            take_id: "take_002".to_string(),
            ..Default::default()
        };
        take2.measured.exposure = ExposurePhysics {
            histogram_mean: 90.0, // Underexposed relative to take 1 (~0.41 stops)
            dynamic_range_stops: 9.8,
            ..Default::default()
        };
        take2.measured.exposure.el_zones.zone_0_black_pct = 4.2;
        take2.measured.color = ColorPhysics {
            estimated_kelvin: 6200.0, // Cooler (+600K) relative to take 1
            saturation_mean: 0.28,
            delta_e_d65: 3.8,
            ..Default::default()
        };

        let report = compute_cross_angle_setup_matching("Scene_01", &[take1, take2]);
        assert_eq!(report.hero_master_take_id, "take_001");
        assert_eq!(report.total_takes, 2);
        assert_eq!(report.pairwise_matches.len(), 2);

        let delta = &report.pairwise_matches[1];
        assert_eq!(delta.source_take_id, "take_002");
        assert_eq!(delta.target_take_id, "take_001");
        assert!(delta.exposure_stops_delta < 0.0); // take 2 is darker
        assert!(delta.kelvin_delta > 0.0); // take 2 is cooler
        assert!(delta.recommended_cdl.slope[0] > 1.0); // needs gain boost

        let xml = generate_asc_cdl_xml(&delta.recommended_cdl, "take_002", "take_001");
        assert!(xml.contains("<ColorDecisionList"));
        assert!(xml.contains("<Slope>"));
        assert!(xml.contains("<Saturation>"));

        let cube = generate_3d_lut_cube(&delta.recommended_cdl, "TestLUT", 9);
        assert!(cube.contains("LUT_3D_SIZE 9"));
        assert!(cube.contains("DOMAIN_MAX 1.0 1.0 1.0"));
    }
}
