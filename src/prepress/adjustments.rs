//! Explicit RGB adjustment operators on observed process colour; spot inks stay native.
use super::*;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Policy {
    ProfiledProcessPreserveSpots,
}

pub(crate) fn receipt() -> Value {
    json!({"policy":"profiled_process_preserve_spots","space":"output_CMYK_profile_AToB_to_encoded_sRGB;existing_ordered_RGB_operators_and_RGB_blend;BToA_to_process","range":"observed_linear_RGB_clipped_before_sRGB_encoding","alpha":"unchanged","spots":"amount_identity_and_retention_unchanged;excluded_from_RGB_observation","backdrop":"current_actual_container_backdrop;contextual_process_delta_preserves_ambient_coverage","clipped":"intrinsic_base_conditional_process;close_modified_process_channels_at_base_alpha_before_base_controls","identity":"unchanged_RGB_result_preserves_exact_original_ink_amounts","source_changed":false})
}
impl Context<'_> {
    pub(super) fn clipped_adjustments(
        &self,
        i: usize,
        base: &mut Surface,
        initial: Option<&Surface>,
    ) -> Result<(), Error> {
        let siblings = scene::children(self.document, self.document.items[i].parent.as_deref());
        let position = siblings.iter().position(|&j| j == i).unwrap();
        for &j in &siblings[position + 1..] {
            if nonprinting(&self.document.items[j]) {
                continue;
            }
            if !matches!(&self.document.items[j].content,Content::Adjustment{adjustment} if adjustment.clip_to.is_some())
            {
                break;
            }
            self.adjust(j, base, initial, true)?;
        }
        Ok(())
    }
    pub(super) fn adjust(
        &self,
        i: usize,
        surface: &mut Surface,
        initial: Option<&Surface>,
        clipped: bool,
    ) -> Result<(), Error> {
        self.control.check()?;
        let item = &self.document.items[i];
        if !item.visible || item.opacity == 0.0 {
            return Ok(());
        }
        let Content::Adjustment { adjustment } = &item.content else {
            unreachable!()
        };
        let observer = self
            .observer
            .as_ref()
            .expect("Prepared adjustment observer");
        let world = scene::world_transform(self.document, i)?;
        let clip = item
            .clip
            .as_ref()
            .filter(|c| c.enabled)
            .map(|c| {
                self.mask(
                    &c.geometry,
                    c.fill_rule,
                    geometry::multiply(world, c.transform),
                )
            })
            .transpose()?;
        let mask = item
            .mask
            .as_ref()
            .filter(|m| m.enabled)
            .map(|m| crate::masks::prepare(m, world))
            .transpose()?;
        let n = self.channels();
        let pixels = surface.values.len() / (n + 1);
        for start in (0..pixels).step_by(4096) {
            self.control.check()?;
            let end = (start + 4096).min(pixels);
            let mut inks = Vec::with_capacity((end - start) * 4);
            let mut weights = Vec::with_capacity(end - start);
            let mut alphas = Vec::with_capacity(end - start);
            for pixel in start..end {
                let at = pixel * (n + 1);
                let own = surface.values[at + n];
                let ambient = initial.map_or(0.0, |b| b.values[at + n]);
                let alpha = if clipped {
                    own
                } else {
                    own + (1.0 - own) * ambient
                };
                alphas.push(alpha);
                let weight = item.opacity
                    * clip
                        .as_ref()
                        .map_or(1.0, |m| m.data()[pixel] as f64 / 255.0)
                    * mask.as_ref().map_or(1.0, |m| m.sample(self.point(pixel)))
                    * self.artwork_masks.get(&item.id).map_or(1.0, |m| m[pixel]);
                weights.push(if alpha == 0.0 { 0.0 } else { weight });
                for c in 0..4 {
                    let ambient = initial.map_or(0.0, |b| b.values[at + c]);
                    let retained =
                        (if clipped { own } else { 1.0 }) - surface.removal[pixel * n + c];
                    inks.push(if alpha == 0.0 {
                        0.0
                    } else {
                        ((surface.values[at + c] + retained * ambient) / alpha).clamp(0.0, 1.0)
                    });
                }
            }
            let before = observer.process_rgb(&inks)?;
            let mut rgb = before.clone();
            let mut changed = vec![false; end - start];
            for (j, p) in rgb.as_chunks_mut::<3>().0.iter_mut().enumerate() {
                if weights[j] == 0.0 {
                    continue;
                }
                let old = *p;
                let adjusted = crate::adjustments::evaluate(old, adjustment);
                let mixed = crate::blending::mix(old, adjusted, item.blend);
                for c in 0..3 {
                    p[c] = (old[c] + weights[j] * (mixed[c] - old[c])).clamp(0.0, 1.0);
                }
                changed[j] = *p != old;
            }
            let converted = self.converter.rgb(&rgb)?;
            for (j, values) in converted.as_chunks::<4>().0.iter().enumerate() {
                if !changed[j] {
                    continue;
                }
                let pixel = start + j;
                let at = pixel * (n + 1);
                let alpha = alphas[j];
                for c in 0..4 {
                    if clipped {
                        surface.values[at + c] = values[c] * alpha;
                        surface.removal[pixel * n + c] = alpha;
                    } else {
                        // A pass-through adjustment may change ambient colour without
                        // adding local alpha. Keep that signed contextual delta; never
                        // turn it into new paint coverage or touch a named ink.
                        surface.values[at + c] += (values[c] - inks[j * 4 + c]) * alpha;
                    }
                }
            }
        }
        self.control.check()
    }
}
