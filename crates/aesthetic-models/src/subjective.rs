//! Layer 3: Subjective & Aesthetic Models
//!
//! Evaluates aesthetic qualities, visual tension, memorability,
//! and correlation with award-winning cinema reference styles.

use serde::{Deserialize, Serialize};

/// Known stylistic visual families derived from cluster analysis.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub enum StyleFamilyCluster {
    #[default]
    Unknown,
    PrestigeNaturalism,
    NeoNoir,
    ChiaroscuroDramatic,
    HighKeyCommercial,
    MutedRealism,
    VibrantStylized,
    MonochromaticMinimalist,
    WarmNostalgic,
    CoolDystopian,
}

/// Creative and subjective aesthetic score factors.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct CreativeAesthetic {
    /// Cosine similarity against Golden Baseline embedding corpus (0.0 - 100.0)
    pub baseline_similarity: f32,
    /// Percentile rank within the identified style family (0.0 - 100.0)
    pub style_family_percentile: f32,
    pub style_family: StyleFamilyCluster,
    /// Compositional and visual tension score (0.0 - 100.0)
    pub visual_tension: f32,
    /// Standalone hero frame potency for portfolio and thumbnail use
    pub hero_frame_potency: f32,
    /// Immediate visual comprehension within 3 seconds
    pub three_second_impact: f32,
    /// Perceived visual distinctiveness / non-repetitive craft
    pub distinctiveness_score: f32,
}
