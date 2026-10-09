use super::*;
use num_rational::BigRational as R;
use num_traits::{ToPrimitive, Zero};

fn rational(time: Time) -> Result<R, Error> {
    if time.num == 0 || time.den == 0 {
        return Err(invalid(
            "Times and frame rates require positive numerator and denominator",
        ));
    }
    Ok(R::new(time.num.into(), time.den.into()))
}
pub(super) fn options(options: &Options) -> Result<usize, Error> {
    // Validate intrinsic rendering choices even during manifest-only inspection.
    // Actual source dimensions and HDR association are checked with the snapshot.
    crate::render_quality::Plan::new(1, 1, options.scale, options.render_options.as_ref())?;
    if !model::valid_id(&options.link_key) {
        return Err(invalid("link_key must be a portable stable ID"));
    }
    let rate = rational(options.frame_rate)?;
    if ![
        (24, 1),
        (25, 1),
        (30, 1),
        (50, 1),
        (60, 1),
        (24000, 1001),
        (30000, 1001),
        (60000, 1001),
    ]
    .iter()
    .any(|&(n, d)| rate == R::new(n.into(), d.into()))
    {
        return Err(Error::new(
            "UNSUPPORTED",
            "Handoff frame rate is not a supported native video clock",
        ));
    }
    let duration = rational(options.duration)?;
    let count = &duration * &rate;
    if duration > R::from_integer(120.into())
        || !count.is_integer()
        || count < R::from_integer(1.into())
        || !(&duration * R::from_integer(48000.into())).is_integer()
    {
        return Err(invalid(
            "Duration must contain at least one complete video frame, last at most 120 seconds, and land on a 48 kHz sample boundary",
        ));
    }
    count
        .to_integer()
        .to_usize()
        .ok_or_else(|| invalid("Output frame count is out of range"))
}
pub(super) type SourceFrame = (
    Option<String>,
    Option<String>,
    Option<crate::sequences::Delay>,
    Time,
);
pub(super) fn source_frames(d: &Document, options: &Options) -> Result<Vec<SourceFrame>, Error> {
    let sequence = d.variants.as_ref().and_then(|v| v.sequence.as_ref());
    let frame = |f: &crate::sequences::Frame| -> Result<SourceFrame, Error> {
        if f.delay.numerator == 0 {
            return Err(Error::new(
                "UNSUPPORTED",
                "Zero-delay source frames have consumer-dependent timing and cannot be handed off implicitly",
            ));
        }
        Ok((
            Some(f.id.clone()),
            Some(f.dataset.clone()),
            Some(f.delay),
            Time {
                num: f.delay.numerator.into(),
                den: if f.delay.denominator == 0 {
                    100
                } else {
                    f.delay.denominator.into()
                },
            },
        ))
    };
    match &options.selection {
        Selection::Sequence => sequence
            .ok_or_else(|| invalid("Sequence selection requires an ordered source sequence"))?
            .frames
            .iter()
            .map(frame)
            .collect(),
        Selection::Still { frame_id: Some(id) } => {
            let f = sequence
                .and_then(|s| s.frames.iter().find(|f| f.id == *id))
                .ok_or_else(|| invalid("Selected source frame does not exist"))?;
            Ok(vec![(
                Some(f.id.clone()),
                Some(f.dataset.clone()),
                Some(f.delay),
                options.duration,
            )])
        }
        Selection::Still { frame_id: None } => {
            if sequence.is_some() {
                return Err(invalid(
                    "A still from a sequence requires an explicit frame_id",
                ));
            }
            Ok(vec![(None, None, None, options.duration)])
        }
    }
}
pub(super) fn schedule(
    options: &Options,
    holds: &[Time],
    control: &Control,
) -> Result<Vec<Option<usize>>, Error> {
    let count = self::options(options)?;
    if holds.is_empty() || holds.len() > crate::sequences::MAX_FRAMES {
        return Err(invalid("Expected 1..256 frame holds"));
    }
    if matches!(options.selection, Selection::Still { .. })
        && (holds.len() != 1 || holds[0] != options.duration)
    {
        return Err(invalid(
            "A still must hold its one frame for the complete destination duration",
        ));
    }
    let rate = rational(options.frame_rate)?;
    let mut cycle = R::zero();
    let mut ends = Vec::new();
    for &hold in holds {
        let hold = rational(hold)?;
        if options.timing == Timing::Strict && !(&hold * &rate).is_integer() {
            return Err(Error::new(
                "UNALIGNED_TIME",
                "A strict source hold must land on the destination frame clock; explicitly choose sample_start to resample",
            ));
        }
        cycle += hold;
        ends.push(cycle.clone());
    }
    let mut selected = Vec::with_capacity(count);
    for i in 0..count {
        if i % 32 == 0 {
            control.check()?;
        }
        let mut time = R::from_integer(i.into()) / &rate;
        if time >= cycle {
            match options.end {
                Ending::HoldLast => {
                    selected.push(Some(holds.len() - 1));
                    continue;
                }
                Ending::Transparent => {
                    selected.push(None);
                    continue;
                }
                Ending::Loop => time -= &cycle * R::from_integer((&time / &cycle).to_integer()),
            }
        }
        selected.push(ends.iter().position(|end| time < *end));
    }
    control.check()?;
    Ok(selected)
}
