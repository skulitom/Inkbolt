//! Original explicit first-line placement over pinned font-instance metrics.
use super::*;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum FirstBaselineMetric {
    Ascent,
    CapHeight,
    XHeight,
    Leading,
    Fixed,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct FirstBaseline {
    pub metric: FirstBaselineMetric,
    #[serde(default)]
    pub minimum: f64,
}
impl FirstBaseline {
    pub(super) fn validate(self) -> Result<(), Error> {
        if !self.minimum.is_finite() || !(0.0..=MAX_COORDINATE).contains(&self.minimum) {
            return Err(invalid(
                "First baseline minimum must be in 0..=32768 local pixels",
            ));
        }
        Ok(())
    }
    pub(super) fn font_height(self, face: &rustybuzz::Face<'_>, size: f64) -> Result<f64, Error> {
        let height = match self.metric {
            FirstBaselineMetric::CapHeight => face.capital_height(),
            FirstBaselineMetric::XHeight => face.x_height(),
            _ => return Ok(0.0),
        }.filter(|&v| v > 0).ok_or_else(|| Error::new("FONT_METRIC_MISSING",
            "First-baseline cap height or x-height requires a positive metric in every contributing pinned font instance; choose another metric or an explicit fixed offset"))?;
        Ok(height as f64 * size / face.units_per_em() as f64)
    }
    pub(super) fn offset(self, ascent: f64, leading: f64, height: f64) -> f64 {
        let value = match self.metric {
            FirstBaselineMetric::Ascent => ascent,
            FirstBaselineMetric::CapHeight | FirstBaselineMetric::XHeight => height,
            FirstBaselineMetric::Leading => leading,
            FirstBaselineMetric::Fixed => 0.0,
        };
        value.max(self.minimum)
    }
}
