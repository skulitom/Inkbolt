//! Precision selection and separate certificates for the stages of a combination.
use super::*;

struct Solution {
    inputs: Vec<Operand>,
    emitted: Option<output::Path>,
    curves: Value,
    arrangement: Arrangement,
    rounded: Vec<Vec<Point>>,
    rounding: R,
    output_snaps: Vec<R>,
}

fn exact(
    mut inputs: Vec<Operand>,
    mode: Mode,
    tolerance: &R,
    budget: &mut Budget,
    reduced: bool,
    output: Output,
) -> Result<Solution, (Box<Error>, &'static str)> {
    if reduced {
        budget.maximum = crate::limits::booleans::AUTO_CURVE_WORK;
    }
    let mut sources = output.sources();
    let curves = curves::evaluate(&mut inputs, &(tolerance * tolerance), &mut sources, budget);
    budget.maximum = MAX_WORK;
    let curves = curves.map_err(|e| (Box::new(e), "curves"))?;
    let arrangement =
        arrange(&inputs, mode, &sources, true, budget).map_err(|e| (Box::new(e), "arrangement"))?;
    let (rounded, rounding) = round_junctions(
        &arrangement.loops,
        sources.as_ref().map(|_| &arrangement.junctions.positions),
        budget,
    )
    .map_err(|e| (Box::new(e), "output"))?;
    let emitted = (output == Output::Curves)
        .then(|| output::materialize(&arrangement, &rounded, tolerance, true, budget))
        .transpose()
        .map_err(|e| (Box::new(e), "output"))?;
    Ok(Solution {
        inputs,
        emitted,
        curves,
        arrangement,
        rounded,
        rounding,
        output_snaps: vec![],
    })
}

fn approximate(
    mut inputs: Vec<Operand>,
    mode: Mode,
    requested: f64,
    output: Output,
    budget: &mut Budget,
) -> Result<Solution, Error> {
    let tolerance = r(requested);
    let grid = tolerance::grid(requested);
    let mut sources = output.sources();
    let curves = tolerance::evaluate(&mut inputs, &tolerance, &grid, &mut sources, budget)?;
    let mut arrangement = arrange(&inputs, mode, &sources, false, budget)?;
    let mut output_snaps = Vec::new();
    loop {
        match rounding(&arrangement.loops, budget) {
            Ok((rounded, rounding)) => {
                if rounding > &tolerance * &tolerance / n(64) {
                    return Err(Error::new(
                        "PRECISION_LOSS",
                        "Boolean output rounding exceeds its tolerance budget",
                    ));
                }
                let emitted = (output == Output::Curves)
                    .then(|| output::materialize(&arrangement, &rounded, &tolerance, false, budget))
                    .transpose()?;
                return Ok(Solution {
                    inputs,
                    emitted,
                    curves,
                    arrangement,
                    rounded,
                    rounding,
                    output_snaps,
                });
            }
            Err(e)
                if e.code == "PRECISION_LOSS"
                    && output_snaps.len() < crate::limits::booleans::MAX_OUTPUT_SNAP_PASSES =>
            {
                let (repaired, deviation) = tolerance::repair(&arrangement.loops, &grid, budget)?;
                arrangement = repaired;
                output_snaps.push(deviation);
            }
            Err(e) => return Err(e),
        }
    }
}

pub(super) fn compute(
    document: &Document,
    ids: &[String],
    mode: Mode,
    options: Options,
    output: Output,
    inputs: Vec<Operand>,
) -> Result<Value, Error> {
    let mut budget = Budget::default();
    let mut fallback = None;
    let (solution, certificate) = if options.precision == Precision::Tolerance {
        (
            approximate(inputs, mode, options.curve_tolerance, output, &mut budget)?,
            "tolerance_snap",
        )
    } else {
        match exact(
            inputs.clone(),
            mode,
            &r(options.curve_tolerance),
            &mut budget,
            options.precision == Precision::Auto,
            output,
        ) {
            Ok(solution) => (solution, "exact"),
            Err((e, stage)) => {
                let eligible = matches!(
                    e.code,
                    "CURVE_TOPOLOGY_UNRESOLVED" | "PRECISION_LOSS" | "TOPOLOGY_ERROR"
                ) || (stage == "curves" && e.code == "RESOURCE_LIMIT");
                if options.precision != Precision::Auto
                    || options.curve_tolerance == 0.0
                    || !eligible
                {
                    return Err(*e);
                }
                fallback = Some(json!({"stage":stage,"code":e.code,"message":e.message,
                    "attempt_work_units":budget.used}));
                (
                    approximate(inputs, mode, options.curve_tolerance, output, &mut budget)?,
                    "tolerance_snap",
                )
            }
        }
    };
    let Solution {
        inputs,
        emitted,
        curves,
        arrangement,
        rounded,
        rounding,
        output_snaps,
    } = solution;
    let summaries: Vec<_> = ids
        .iter()
        .zip(&inputs)
        .map(|(id, input)| {
            let mut value = json!({"id":id,"flattened_edges":input.edges.len(),
            "flattening_deviation_squared":input.maximum.to_string(),"fill_rule":input.rule});
            if certificate == "tolerance_snap" {
                value["snapping_deviation_squared"] = json!(input.snapping.to_string());
            }
            if let Some(conversion) = &input.conversion {
                value["primitive_conversion"] = conversion.clone();
            }
            value
        })
        .collect();
    let (mut commands, curve_report) = if let Some(path) = emitted {
        (path.commands, Some(path.report))
    } else {
        (Vec::new(), None)
    };
    if curve_report.is_none() {
        for points in &rounded {
            commands.push(PathCommand::Move { to: points[0] });
            commands.extend(points[1..].iter().map(|p| PathCommand::Line { to: *p }));
            commands.push(PathCommand::Close {});
        }
    }
    let geometry = if commands.is_empty() {
        None
    } else {
        let g = Geometry::Path { commands };
        crate::geometry::validate_geometry(&g)?;
        Some(g)
    };
    let approximate = certificate == "tolerance_snap";
    let mut losses = vec![
        "This is a geometry-only result. Paint, strokes, masks, clips, filters, visibility and opacity do not define operands. Sources are unchanged.",
        if approximate {
            "Curves are flattened and snapped with declared displacement bounds. Source topology is not preserved: small regions, gaps and contacts may merge, split or disappear. Exact topology checks apply to the snapped arrangement and its rounded output."
        } else {
            "Curved boundaries become chords only after an exact simultaneous-deformation certificate. Tolerance bounds each input arc, not movement of intersection vertices or the final boolean boundary. Collinear retracing is reduced by exact filled winding; source strokes and zero-area traces are not retained."
        },
        "Output vertices are rounded to f64 with explicit planarity, winding, nesting and adjacency checks. Exact area refers to the rational arrangement before this rounding.",
    ];
    if approximate {
        losses.push("Deviation bounds apply to input curve flattening, input snapping, each output repair and final rounding separately. They do not bound intersection movement or the final boolean boundary; nearly parallel intersections can move farther. Output repairs use nonzero self-union and may change topology again.");
    }
    if inputs.iter().any(|input| input.conversion.is_some()) {
        losses.push("Analytic ellipses expand to four tangent cubics. Each input reports its affine world-space conversion error separately from curve tolerance. Curve certificates do not certify analytic ellipse contacts; source primitives remain unchanged.");
    }
    let exact_area: R = arrangement.loops.iter().map(|p| area(p)).sum();
    let mut result = json!({
        "document_id":document.id,"revision":document.revision,"source_ids":ids,"mode":mode,
        "precision":options.precision,"certificate":certificate,
        "geometry":geometry,"fill_rule":"nonzero","coordinates":"document_root",
        "empty":arrangement.loops.is_empty(),"area_exact":exact_area.to_string(),"area":exact_area.to_f64(),
        "positive_contours":arrangement.loops.iter().filter(|p|area(p)>R::zero()).count(),
        "negative_contours":arrangement.loops.iter().filter(|p|area(p)<R::zero()).count(),
        "input_model":if approximate { "world_space_closed_geometry_with_bounded_snapped_chords" }
            else { "world_space_closed_geometry_with_exact_certified_cubic_flattening" },
        "curve_tolerance":options.curve_tolerance,"inputs":summaries,"curves":curves,
        "rounding_deviation_squared":rounding.to_string(),"atomic_edges":arrangement.atoms,
        "boundary_edges":arrangement.boundary,"work_units":budget.used,"losses":losses
    });
    if let Some(report) = curve_report {
        result["output"] = json!("curves");
        result["curve_output"] = report;
        result["curve_output"]["resolved_transverse_junctions"] =
            json!(arrangement.junctions.positions.len());
        result["losses"][1] = if approximate {
            json!(
                "Curves follow source intervals selected by the snapped polygon arrangement. Their endpoint handles follow the snapped junctions. Small regions and contacts can change during input flattening and snapping."
            )
        } else {
            json!(
                "The exact certified arrangement selects source subcurves. Editable control coordinates are rounded to binary64 with a reported deviation bound."
            )
        };
        result["losses"][2] = json!(
            "area_exact measures the reference polygon. curve_output.signed_area_exact integrates the emitted line and cubic contours."
        );
    }
    if let Some(fallback) = fallback {
        result["fallback"] = fallback;
    }
    if approximate {
        result["output_snap_deviation_squared"] = json!(
            output_snaps
                .iter()
                .map(ToString::to_string)
                .collect::<Vec<_>>()
        );
        result["output_rounding_limit_squared"] =
            json!((r(options.curve_tolerance).pow(2) / n(64)).to_string());
    }
    Ok(result)
}
