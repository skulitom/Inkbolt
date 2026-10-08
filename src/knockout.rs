//! Original footprint-aware group replacement in premultiplied encoded sRGB.
use crate::{
    Error,
    model::{BlendMode, Content, Document},
    scene,
};

pub(crate) fn validate(document: &Document) -> Result<(), Error> {
    for (i, item) in document.items.iter().enumerate() {
        if matches!(&item.content, Content::Adjustment { adjustment } if adjustment.clip_to.is_none())
            && scene::ancestors(document, i)?
                .iter()
                .any(|&p| document.items[p].content.is_knockout())
        {
            return Err(Error::new("UNSUPPORTED", "Backdrop adjustments inside knockout groups require an explicit footprint; bind the adjustment to a drawable item").at_item(&item.id));
        }
    }
    Ok(())
}

pub(crate) fn active(document: &Document) -> bool {
    document.items.iter().any(|i| i.content.is_knockout())
}
pub(crate) fn work(document: &Document, scale: u32) -> u64 {
    if !active(document) {
        return 0;
    }
    document
        .items
        .iter()
        .map(|i| 24 + crate::filters::work(i, scale) + crate::effects::work(i, scale))
        .sum()
}
pub(crate) fn composite(
    dst: &mut [f64; 4],
    src: [f64; 4],
    shape: f64,
    initial: [f64; 4],
    mode: BlendMode,
) {
    let a = src[3];
    let f = shape.max(a).clamp(0.0, 1.0);
    let b = initial[3];
    let color = if b == 0.0 {
        [0.0; 3]
    } else {
        std::array::from_fn(|c| initial[c] / b)
    };
    let blend = crate::blending::mix(color, [src[0], src[1], src[2]], mode);
    dst[3] = ((1.0 - f) * dst[3] + (f - a) * b + a).clamp(0.0, 1.0);
    for c in 0..3 {
        dst[c] =
            ((1.0 - f) * dst[c] + (f - a) * initial[c] + a * ((1.0 - b) * src[c] + b * blend[c]))
                .clamp(0.0, dst[3]);
    }
}
