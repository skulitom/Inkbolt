//! Exact selection readers shared by authoring, inspection and local edits.
use super::*;
use crate::{native_pixels::Budget, sample_store::private::Rows, scalar_store, stored_scalars};
use sha2::{Digest, Sha256};

pub(crate) struct Prepared {
    width: u32,
    height: u32,
    inline: Vec<u8>,
    native: Option<stored_scalars::Reader>,
}
impl Prepared {
    pub(crate) fn new(
        s: &Selection,
        root: Option<&Path>,
        control: &Control,
    ) -> Result<Self, Error> {
        validate(s, s.width, s.height)?;
        Ok(Self {
            width: s.width,
            height: s.height,
            inline: if s.native.is_none() {
                render::unhex(&s.gray_hex)
            } else {
                Vec::new()
            },
            native: s
                .native
                .as_ref()
                .map(|g| stored_scalars::Reader::new(g, root, control))
                .transpose()?,
        })
    }
    pub(crate) fn for_edit(
        document: &Document,
        enabled: bool,
        root: Option<&Path>,
        work: &mut impl Budget,
        invalid: fn(&str) -> Error,
    ) -> Result<Option<Self>, Error> {
        if !enabled {
            return Ok(None);
        }
        let s = document
            .selection
            .as_ref()
            .ok_or_else(|| invalid("use_selection requires an explicit active selection"))?;
        if s.native.is_some() {
            work.prepare(s.width as u64 * s.height as u64 * 3)?;
        }
        Self::new(s, root, work.control()).map(Some)
    }
    pub(crate) fn at(&self, x: u32, y: u32) -> Result<u8, Error> {
        if x >= self.width || y >= self.height {
            return Ok(0);
        }
        match &self.native {
            Some(reader) => reader.pixel(x, y),
            None => Ok(self.inline[y as usize * self.width as usize + x as usize]),
        }
    }
}

pub(crate) fn selection_memory(document: &Document, enabled: bool) -> u64 {
    if !enabled {
        return 0;
    }
    document.selection.as_ref().map_or(0, |s| {
        s.native.as_ref().map_or(
            s.width as u64 * s.height as u64,
            // Retained tile cache plus one decoded tile/blob during a cache miss.
            |g| {
                g.cache_bytes()
                    + 2 * crate::scalar_store::TILE_EDGE.pow(2) as u64
                    + crate::limits::sample_store::HEADER_BYTES as u64
            },
        )
    })
}

/// Explicit bounded materialization for existing small-canvas consumers.
pub(crate) fn dense(
    s: &Selection,
    root: Option<&Path>,
    control: &Control,
) -> Result<Vec<u8>, Error> {
    let n = check_size(s.width, s.height)?;
    let mut rows = SourceRows::new(s, root, control)?;
    let mut bytes = vec![0; n];
    for (y, row) in bytes.chunks_mut(s.width as usize).enumerate() {
        rows.read(y as u32, row, control)?;
    }
    Ok(bytes)
}

pub(super) enum SourceRows {
    Inline { width: usize, bytes: Vec<u8> },
    Native(Rows<scalar_store::Spec>),
}
impl SourceRows {
    pub(super) fn new(
        s: &Selection,
        root: Option<&Path>,
        control: &Control,
    ) -> Result<Self, Error> {
        validate(s, s.width, s.height)?;
        Ok(match &s.native {
            Some(grid) => Self::Native(Rows::new(grid.prepare(root, control)?, root)),
            None => Self::Inline {
                width: s.width as usize,
                bytes: render::unhex(&s.gray_hex),
            },
        })
    }
    pub(super) fn read(&mut self, y: u32, row: &mut [u8], control: &Control) -> Result<(), Error> {
        control.check()?;
        match self {
            Self::Native(rows) => rows.read(y, row, control),
            Self::Inline { width, bytes } => {
                let start = y as usize * *width;
                if row.len() != *width || start + row.len() > bytes.len() {
                    return Err(invalid("Selection row is outside the source"));
                }
                row.copy_from_slice(&bytes[start..start + *width]);
                Ok(())
            }
        }
    }
}

pub(crate) fn generate(
    width: u32,
    height: u32,
    prior: Option<&Selection>,
    root: Option<&Path>,
    control: &Control,
    read_row: impl FnMut(u32, &mut [u8]) -> Result<(), Error>,
) -> Result<Selection, Error> {
    let spec = scalar_store::Spec { width, height };
    spec.validate()?;
    let candidate = if let Some(grid) = prior
        .and_then(|s| s.native.as_ref())
        .filter(|g| g.base.spec == spec)
    {
        grid.prepare(root, control)?
            .map_private_rows(control, read_row)?
    } else {
        scalar_store::Candidate::from_private_rows(spec, control, read_row)?
    };
    Ok(Selection {
        width,
        height,
        gray_hex: String::new(),
        native: Some(stored_scalars::Grid::from_candidate(candidate)),
    })
}

pub(super) fn inspect(
    s: &Selection,
    root: Option<&Path>,
    control: &Control,
) -> Result<Value, Error> {
    let mut rows = SourceRows::new(s, root, control)?;
    let mut row = vec![0; s.width as usize];
    let mut digest = Sha256::new();
    let mut b = [s.width, s.height, 0, 0];
    let (mut selected, mut full, mut sum) = (0u64, 0u64, 0u64);
    for y in 0..s.height {
        rows.read(y, &mut row, control)?;
        digest.update(&row);
        for (x, &v) in row.iter().enumerate() {
            sum += v as u64;
            full += u64::from(v == 255);
            if v != 0 {
                selected += 1;
                b = [
                    b[0].min(x as u32),
                    b[1].min(y),
                    b[2].max(x as u32 + 1),
                    b[3].max(y + 1),
                ];
            }
        }
    }
    Ok(
        json!({"width":s.width,"height":s.height,"bounds":(b[2]>b[0]&&b[3]>b[1]).then_some(b),
        "selected_pixels":selected,"fully_selected_pixels":full,"coverage_sum":sum as f64/255.0,
        "sha256":format!("{:x}",digest.finalize()),"coordinates":"document_pixel_grid","bounds_contract":"nonzero_end_exclusive"}),
    )
}
