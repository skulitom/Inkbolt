//! Open-file identity for trusted local filesystems; no SDK sources are included.
use crate::Error;
use serde::{Deserialize, Serialize};
use std::fs::File;

#[derive(Clone, Debug, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Identity {
    pub volume: u64,
    pub file: [u8; 16],
}

#[cfg(windows)]
pub(super) fn identify(file: &File) -> Result<Identity, Error> {
    use std::{ffi::c_void, os::windows::io::AsRawHandle};
    #[repr(C)]
    struct FileIdInfo {
        volume: u64,
        id: [u8; 16],
    }
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetFileInformationByHandleEx(
            handle: *mut c_void,
            class: i32,
            info: *mut c_void,
            size: u32,
        ) -> i32;
    }
    let mut info = FileIdInfo {
        volume: 0,
        id: [0; 16],
    };
    // FileIdInfo = 18; the live File owns this handle. The 24-byte C buffer has the
    // documented u64 volume and 128-bit ID layout and outlives the synchronous call.
    let ok = unsafe {
        GetFileInformationByHandleEx(
            file.as_raw_handle(),
            18,
            (&mut info as *mut FileIdInfo).cast(),
            std::mem::size_of::<FileIdInfo>() as u32,
        )
    };
    if ok == 0 {
        return Err(Error::new(
            "IO_ERROR",
            "Filesystem cannot provide the file identity required for durable publication",
        ));
    }
    Ok(Identity {
        volume: info.volume,
        file: info.id,
    })
}
#[cfg(unix)]
pub(super) fn identify(file: &File) -> Result<Identity, Error> {
    use std::os::unix::fs::MetadataExt;
    let metadata = file.metadata().map_err(|_| {
        Error::new(
            "IO_ERROR",
            "Unable to read durable publication file identity",
        )
    })?;
    // Keep the existing receipt layout. Device identifies the filesystem, and
    // the inode occupies the low eight bytes of the 128-bit little-endian ID.
    // Read from the held file, never a second path lookup. A retained hard link
    // keeps this inode allocated throughout prepared-publication recovery.
    Ok(Identity {
        volume: metadata.dev(),
        file: u128::from(metadata.ino()).to_le_bytes(),
    })
}
#[cfg(not(any(windows, unix)))]
pub(super) fn identify(_file: &File) -> Result<Identity, Error> {
    Err(Error::new(
        "UNSUPPORTED_PLATFORM",
        "Durable publication requires a Windows or Unix file-identity backend",
    ))
}
