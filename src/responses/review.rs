use crate::{Error, ExportFormat, Request, control::Control, publish, workspace::Workspace};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::PathBuf;

/// Save the full dry run and return its proposal and change summary. In a workspace use {"file_name":"review.json"}. Otherwise also supply an absolute output_root.
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ReviewOutput {
    /// Existing directory. Defaults to the selected workspace.
    pub output_root: PathBuf,
    /// New portable .json filename, for example review.json.
    pub file_name: String,
}

impl ReviewOutput {
    pub(crate) fn schema() -> Value {
        json!(schemars::schema_for!(Self))
    }

    pub(crate) fn take(
        value: &mut Value,
        workspace: Option<&Workspace>,
    ) -> Result<Option<Self>, Error> {
        let Some(mut output) = value
            .as_object_mut()
            .and_then(|v| v.remove("review_output"))
        else {
            return Ok(None);
        };
        if value["command"] != "session.dry_run" {
            return Err(Error::new(
                "INVALID_REQUEST",
                "review_output requires session.dry_run",
            ));
        }
        if let Some(w) = workspace {
            crate::workspace::normalize(&mut output, &Self::schema(), w, "session.dry_run", 0)?;
        }
        serde_json::from_value(output).map(Some).map_err(|_| {
            Error::new(
                "INVALID_REQUEST",
                "review_output requires file_name and an output_root outside workspace mode",
            )
        })
    }

    /// Execute the ordinary read-only session review. Only the requested review file is published.
    pub fn publish(&self, request: Request, context: &Control) -> Result<Value, Error> {
        let Request::SessionDryRun { ref control, .. } = request else {
            return Err(Error::new(
                "INVALID_REQUEST",
                "review_output requires session.dry_run",
            ));
        };
        let control = context.scoped(control)?;
        control.check()?;
        let path =
            publish::output_path(&self.output_root, &self.file_name, ExportFormat::Snapshot)?;
        control.check_path(&path)?;
        publish::exists(&path)?;
        if !self.output_root.is_dir() {
            return Err(Error::new(
                "IO_ERROR",
                "Review output_root must be an existing directory",
            ));
        }
        let result = crate::execute_controlled(request, &control)?;
        let mut payload = publish::payload::json_file(&result, &control)?;
        let difference = &result["difference"];
        let items = difference["items"]
            .as_array()
            .expect("session review item differences");
        let summary = json!({
            "dry_run":true, "committed":false, "source_changed":false,
            "base_ref":result["base_ref"], "proposal":result["proposal"], "apply_command":result["apply_command"],
            "difference_summary":{
                "changed":difference["changed"], "from_revision":difference["from_revision"], "to_revision":difference["to_revision"],
                "item_count":items.len(), "first_item":items.first().map(|item|json!({"id":item["id"],"change":item["change"],"fields":item["fields"]})),
                "metadata_count":difference["metadata"].as_array().expect("review metadata differences").len(),
                "resource_count":difference["resources"].as_array().expect("review resource differences").len(),
                "resource_bindings_changed":difference["resource_bindings_changed"], "rendered_pixels":difference["rendered_pixels"]
            },
            "review_file":{"path":path,"bytes":payload.len(),"sha256":payload.sha256()}
        });
        drop(result);
        publish::write_new(&path, &mut payload, &control)?;
        Ok(summary)
    }
}
