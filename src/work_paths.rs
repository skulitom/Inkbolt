//! Nonprinting geometric regions shared by selection and vector-mask workflows.
use crate::{Error, geometry, model::*, scene, selections};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
pub(crate) mod coverage;

pub const MAX_COMPONENTS: usize = 64;
pub const MAX_COMPONENT_DEPTH: usize = 8;
#[derive(Clone, Debug, Deserialize, Serialize, JsonSchema, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Operand {
    pub geometry: Geometry,
    #[serde(default)]
    pub fill_rule: FillRule,
    #[serde(default = "identity")]
    pub transform: Matrix,
}
pub(crate) fn compound_rule(g: &Geometry, rule: FillRule) -> Result<(), Error> {
    if matches!(g, Geometry::Compound { .. }) && rule != FillRule::Nonzero {
        return Err(invalid(
            "Compound regions use per-operand winding; their outer fill_rule must be nonzero",
        ));
    }
    Ok(())
}
pub(crate) fn validate_compound(g: &Geometry) -> Result<usize, Error> {
    fn visit(
        g: &Geometry,
        world: Matrix,
        depth: usize,
        leaves: &mut usize,
    ) -> Result<usize, Error> {
        if depth > MAX_COMPONENT_DEPTH {
            return Err(limit("Compound region exceeds eight nested operations"));
        }
        if let Geometry::Compound { operands, .. } = g {
            if !(2..=16).contains(&operands.len()) {
                return Err(invalid("Compound operations require 2..16 operands"));
            }
            let mut commands = 0;
            for v in operands {
                compound_rule(&v.geometry, v.fill_rule)?;
                geometry::validate_matrix(v.transform)?;
                let matrix = geometry::multiply(world, v.transform);
                geometry::validate_matrix(matrix)?;
                commands += visit(&v.geometry, matrix, depth + 1, leaves)?;
                if commands > MAX_SEGMENTS {
                    return Err(limit("Compound region exceeds 4096 commands"));
                }
            }
            Ok(commands)
        } else {
            *leaves += 1;
            if *leaves > MAX_COMPONENTS {
                return Err(limit("Compound region exceeds 64 leaf components"));
            }
            let commands = geometry::validate_geometry(g)?;
            validate_world_geometry(g, world)?;
            Ok(commands)
        }
    }
    visit(g, identity(), 0, &mut 0)
}
pub(crate) fn combine(
    d: &Document,
    ids: &[String],
    new_id: &str,
    mode: crate::booleans::Mode,
) -> Result<Item, Error> {
    if !(2..=16).contains(&ids.len())
        || ids.iter().collect::<std::collections::HashSet<_>>().len() != ids.len()
    {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Region combination requires 2..16 distinct source IDs",
        ));
    }
    let operands = ids
        .iter()
        .map(|id| {
            let (geometry, fill_rule, transform) = source(d, id)?;
            Ok(Operand {
                geometry,
                fill_rule,
                transform,
            })
        })
        .collect::<Result<Vec<_>, Error>>()?;
    let geometry = Geometry::Compound { mode, operands };
    validate_compound(&geometry)?;
    Ok(serde_json::from_value(json!({"id":new_id,"content":{"type":"work_path","geometry":geometry,"fill_rule":"nonzero"}})).expect("original item fields have valid types"))
}
fn leaf<'a>(
    g: &'a Geometry,
    path: &[usize],
    world: Matrix,
) -> Result<(&'a Geometry, Matrix), Error> {
    if let Some((&index, rest)) = path.split_first() {
        let Geometry::Compound { operands, .. } = g else {
            return Err(Error::new(
                "INVALID_OPERATION",
                "Component index descends through a leaf region",
            ));
        };
        let v = operands.get(index).ok_or_else(|| {
            Error::new(
                "INVALID_OPERATION",
                "Compound component index is out of range",
            )
        })?;
        leaf(&v.geometry, rest, geometry::multiply(world, v.transform))
    } else if matches!(g, Geometry::Compound { .. }) {
        Err(Error::new(
            "INVALID_OPERATION",
            "Choose a leaf component for path editing",
        ))
    } else {
        Ok((g, world))
    }
}
fn leaf_mut<'a>(g: &'a mut Geometry, path: &[usize]) -> &'a mut Geometry {
    if let Some((&index, rest)) = path.split_first() {
        let Geometry::Compound { operands, .. } = g else {
            unreachable!("validated component path")
        };
        leaf_mut(&mut operands[index].geometry, rest)
    } else {
        g
    }
}
pub(crate) fn edit_component(
    d: &mut Document,
    index: usize,
    component: &[usize],
    clip: bool,
    action: &crate::paths::Action,
) -> Result<Option<Value>, Error> {
    if component.len() > MAX_COMPONENT_DEPTH {
        return Err(limit("Component address exceeds eight levels"));
    }
    let world = scene::world_transform(d, index)?;
    let (root, world) = if clip {
        let v = d.items[index]
            .clip
            .as_ref()
            .ok_or_else(|| Error::new("INVALID_OPERATION", "Item has no vector clip"))?;
        (&v.geometry, geometry::multiply(world, v.transform))
    } else {
        let Content::WorkPath { geometry, .. } = &d.items[index].content else {
            return Err(Error::new(
                "INVALID_OPERATION",
                "Component editing requires a work path or explicit clip target",
            ));
        };
        (geometry, world)
    };
    let (g, world) = leaf(root, component, world)?;
    let mut temporary = d.clone();
    let mut item = d.items[index].clone();
    item.parent = None;
    item.transform = world;
    item.content = Content::WorkPath {
        geometry: g.clone(),
        fill_rule: FillRule::Nonzero,
    };
    temporary.items = vec![item];
    let detail = crate::paths::edit(&mut temporary, 0, action)?;
    let Content::WorkPath {
        geometry: result, ..
    } = temporary.items.remove(0).content
    else {
        unreachable!()
    };
    let root = if clip {
        &mut d.items[index].clip.as_mut().unwrap().geometry
    } else {
        let Content::WorkPath { geometry, .. } = &mut d.items[index].content else {
            unreachable!()
        };
        geometry
    };
    *leaf_mut(root, component) = result;
    Ok(Some(
        json!({"component":component,"clip":clip,"path_edit":detail,"other_components_changed":false}),
    ))
}
pub(crate) fn component_anchors(d: &Document, index: usize) -> Result<Vec<Value>, Error> {
    fn visit(g: &Geometry, world: Matrix, address: &mut Vec<usize>, out: &mut Vec<Value>) {
        if let Geometry::Compound { operands, .. } = g {
            for (i, v) in operands.iter().enumerate() {
                address.push(i);
                visit(
                    &v.geometry,
                    geometry::multiply(world, v.transform),
                    address,
                    out,
                );
                address.pop();
            }
        } else if let Geometry::Path { commands } = g {
            for mut anchor in crate::paths::geometry_anchors(commands, world) {
                anchor["component"] = json!(address);
                out.push(anchor);
            }
        }
    }
    let (g, _, world) = source(d, &d.items[index].id)?;
    let mut result = Vec::new();
    visit(&g, world, &mut Vec::new(), &mut result);
    Ok(result)
}

fn source(document: &Document, id: &str) -> Result<(Geometry, FillRule, Matrix), Error> {
    let i = scene::index(document, id)?;
    let (Content::WorkPath {
        geometry,
        fill_rule,
    }
    | Content::Vector {
        geometry,
        fill_rule,
        ..
    }) = &document.items[i].content
    else {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Region source must be a work path or vector geometry",
        )
        .at_item(id));
    };
    Ok((
        geometry.clone(),
        *fill_rule,
        scene::world_transform(document, i)?,
    ))
}

pub(crate) fn select(
    document: &mut Document,
    id: &str,
    combine: selections::Combine,
    antialias: bool,
) -> Result<(), Error> {
    let (geometry, fill_rule, world) = source(document, id)?;
    let values = coverage::evaluate(
        &geometry,
        fill_rule,
        world,
        document.width,
        document.height,
        antialias,
    )?;
    selections::combine_values(document, values, combine)
}

pub(crate) fn clip_from_path(
    document: &mut Document,
    target: usize,
    path_id: &str,
    replace_existing: bool,
) -> Result<(), Error> {
    if document.items[target].clip.is_some() && !replace_existing {
        return Err(Error::new(
            "INVALID_OPERATION",
            "Item already has a clip; explicitly set replace_existing to replace it",
        ));
    }
    let (geometry, fill_rule, world) = source(document, path_id)?;
    // Copy geometry, retaining its current world placement. Later edits to the
    // source path do not affect this independently editable item-local clip.
    let transform = geometry::multiply(
        geometry::inverse(scene::world_transform(document, target)?)?,
        world,
    );
    document.items[target].clip = Some(Clip {
        geometry,
        fill_rule,
        transform,
        enabled: true,
    });
    Ok(())
}
