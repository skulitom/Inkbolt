//! Prepare pixels once; only seekable encoding is replayed for file-free preflight.
use super::*;
use crate::publish::payload::{Payload, Projection};

pub(crate) trait WriteSeek: Write + Seek {}
impl<T: Write + Seek> WriteSeek for T {}

pub(crate) struct Encoding<'a> {
    output: Option<&'a mut dyn WriteSeek>,
    control: &'a crate::control::Control,
    payload: Option<Payload>,
}

impl<'a> Encoding<'a> {
    pub fn once(output: &'a mut dyn WriteSeek, control: &'a crate::control::Control) -> Self {
        Self {
            output: Some(output),
            control,
            payload: None,
        }
    }
    pub fn preflight(control: &'a crate::control::Control) -> Self {
        Self {
            output: None,
            control,
            payload: None,
        }
    }
    pub fn run(
        &mut self,
        mut encode: impl FnMut(&mut dyn WriteSeek) -> Result<(), Error>,
    ) -> Result<(), Error> {
        if let Some(output) = &mut self.output {
            return encode(*output);
        }
        let mut first = Projection::new(self.control);
        let result = encode(&mut first);
        first.encoded(result)?;
        let mut second = first.replay()?;
        let result = encode(&mut second);
        second.encoded(result)?;
        self.payload = Some(second.finish()?);
        Ok(())
    }
    pub fn finish(self) -> Result<Payload, Error> {
        self.payload
            .ok_or_else(|| Error::new("EXPORT_ERROR", "Missing TIFF preflight encoding"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::SeekFrom;
    #[test]
    fn encoding_replay_rejects_mutation_even_when_final_bytes_match() {
        let control = crate::control::Control::default();
        let mut encoding = Encoding::preflight(&control);
        let mut pass = 0u8;
        let result = encoding.run(|output| {
            pass += 1;
            output.write_all(&[pass]).unwrap();
            output.seek(SeekFrom::Start(0)).unwrap();
            output.write_all(&[9]).unwrap();
            Ok(())
        });
        assert_eq!(pass, 2);
        assert_eq!(result.unwrap_err().code, "EXPORT_ERROR");
        assert!(encoding.finish().is_err());
    }
    #[test]
    fn first_and_second_pass_errors_preserve_original_failure_and_discard_output() {
        for failing_pass in [1, 2] {
            let control = crate::control::Control::default();
            let mut encoding = Encoding::preflight(&control);
            let mut pass = 0;
            let result = encoding.run(|output| {
                pass += 1;
                output.write_all(b"unfinished").unwrap();
                if pass == failing_pass {
                    Err(Error::new("ORIGINAL_FAILURE", "Original synthetic failure"))
                } else {
                    Ok(())
                }
            });
            assert_eq!(pass, failing_pass);
            assert_eq!(result.unwrap_err().code, "ORIGINAL_FAILURE");
            assert!(encoding.finish().is_err());
        }
    }
}
