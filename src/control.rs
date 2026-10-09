//! Cooperative cancellation and deadlines, shared by CLI and future agent adapters.
use crate::Error;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::{
    path::PathBuf,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};
pub const MAX_TIMEOUT_MS: u64 = 60_000;
#[derive(Clone, Debug, Default, Deserialize, Serialize, JsonSchema)]
#[serde(default, deny_unknown_fields)]
pub struct Options {
    pub timeout_ms: Option<u64>,
    pub cancel_file: Option<PathBuf>,
}
#[derive(Clone, Default)]
pub struct Control {
    cancelled: Arc<AtomicBool>,
    deadline: Option<Instant>,
    cancel_files: Vec<PathBuf>,
    workspace: Option<crate::workspace::Workspace>,
}
impl Control {
    pub(crate) fn has_workspace(&self) -> bool {
        self.workspace.is_some()
    }

    pub(crate) fn in_workspace(&self, workspace: Option<&crate::workspace::Workspace>) -> Self {
        let mut control = self.clone();
        if let Some(workspace) = workspace {
            control.workspace = Some(workspace.clone());
        }
        control
    }

    pub(crate) fn check_resource_paths(
        &self,
        resources: &crate::sessions::Resources,
    ) -> Result<(), Error> {
        if let Some(workspace) = &self.workspace {
            for root in resources
                .asset_root
                .iter()
                .chain(resources.font_root.iter())
            {
                workspace.resolve(root)?;
            }
        }
        Ok(())
    }
    pub fn new(options: &Options) -> Result<Self, Error> {
        Self::default().scoped(options)
    }
    pub fn scoped(&self, options: &Options) -> Result<Self, Error> {
        if options.timeout_ms.is_some_and(|ms| ms > MAX_TIMEOUT_MS) {
            return Err(Error::new(
                "INVALID_REQUEST",
                "Timeout must be in 0..=60000 milliseconds",
            ));
        }
        if let Some(path) = &options.cancel_file {
            crate::assets::absolute(path)?;
            if path.as_os_str().len() > 4096 {
                return Err(Error::new(
                    "RESOURCE_LIMIT",
                    "Cancellation path is too long",
                ));
            }
        }
        let mut cancel_files = self.cancel_files.clone();
        if let Some(path) = &options.cancel_file
            && !cancel_files.contains(path)
        {
            cancel_files.push(path.clone());
        }
        if cancel_files.len() > 4 {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "At most four scoped cancellation markers are supported",
            ));
        }
        let requested = options
            .timeout_ms
            .map(|ms| Instant::now() + Duration::from_millis(ms));
        let deadline = match (self.deadline, requested) {
            (Some(a), Some(b)) => Some(a.min(b)),
            (a, b) => a.or(b),
        };
        Ok(Self {
            cancelled: self.cancelled.clone(),
            deadline,
            cancel_files,
            workspace: self.workspace.clone(),
        })
    }

    pub fn is_cancelled(&self) -> bool {
        self.cancelled.load(Ordering::Acquire)
    }
    pub fn cancel(&self) {
        self.cancelled.store(true, Ordering::Release);
    }
    pub fn check(&self) -> Result<(), Error> {
        let marker = self
            .cancel_files
            .iter()
            .map(|p| p.try_exists())
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| Error::new("IO_ERROR", "Unable to inspect cancellation marker"))?
            .into_iter()
            .any(|v| v);
        if self.cancelled.load(Ordering::Acquire) || marker {
            return Err(Error::new(
                "CANCELLED",
                "Operation cancelled before publication",
            ));
        }
        if self.deadline.is_some_and(|t| Instant::now() >= t) {
            return Err(Error::new(
                "TIMEOUT",
                "Operation deadline reached before publication",
            ));
        }
        Ok(())
    }
}
