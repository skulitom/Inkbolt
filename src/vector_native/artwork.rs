//! Direct editable geometry from an explicitly admitted data-operator subset.
use super::{
    tokens::{self, Token},
    *,
};
use crate::model::{Document, ResourceProfile};
use serde_json::{Value, json};

pub fn read(
    data: &[u8],
    id: String,
    profile: ResourceProfile,
    control: &Control,
) -> Result<Value, Error> {
    fn marker(data: &[u8], wanted: &[u8]) -> Result<(usize, usize), Error> {
        let mut found = None;
        let mut at = 0;
        for line in data.split_inclusive(|v| matches!(v, b'\r' | b'\n')) {
            if line.trim_ascii_end() == wanted && found.replace((at, at + line.len())).is_some() {
                return Err(invalid("Duplicate native section marker"));
            }
            at += line.len();
        }
        found.ok_or_else(|| invalid("Missing native section marker"))
    }
    let (prolog, ps) = marker(data, b"%%BeginProlog")?;
    let (pe, _) = marker(data, b"%%EndProlog")?;
    let (setup, ss) = marker(data, b"%%BeginSetup")?;
    let (se, body) = marker(data, b"%%EndSetup")?;
    let (end, tail) = marker(data, b"%%PageTrailer")?;
    if !(prolog < ps
        && ps <= pe
        && pe < setup
        && setup < ss
        && ss <= se
        && se < body
        && body <= end)
    {
        return Err(invalid("Native sections are out of order"));
    }
    if data[ps..pe]
        .split(|v| matches!(v, b'\r' | b'\n'))
        .any(|line| !line.trim_ascii().is_empty() && !line.trim_ascii_start().starts_with(b"%"))
    {
        return Err(unsupported("Executable native prologs are unsupported"));
    }
    let header = &data[..prolog];
    let header_value = |prefix: &[u8]| -> Result<f64, Error> {
        let mut found = None;
        for line in header.split(|v| matches!(v, b'\r' | b'\n')) {
            if let Some(value) = line.strip_prefix(prefix) {
                let value = std::str::from_utf8(value.trim_ascii())
                    .ok()
                    .and_then(|s| s.parse::<f64>().ok())
                    .filter(|n| n.is_finite())
                    .ok_or_else(|| invalid("Invalid native header number"))?;
                if found.replace(value).is_some() {
                    return Err(invalid("Duplicate native header field"));
                }
            }
        }
        found.ok_or_else(|| unsupported("Required native header declaration is missing"))
    };
    if header_value(b"%AI9_ColorModel:")? != 1.0 {
        return Err(unsupported(
            "Only explicitly interpreted native RGB artwork is supported",
        ));
    }
    if header_value(b"%AI24_LargeCanvasScale:")? != 1.0 {
        return Err(unsupported("Scaled native canvases are unsupported"));
    }
    let expected_layers = header_value(b"%AI5_NumLayers:")?;
    let boards = boards::read(&data[ss..se], control)?;
    let left = boards
        .iter()
        .map(|b| b.bounds[0])
        .fold(f64::INFINITY, f64::min);
    let top = boards
        .iter()
        .map(|b| b.bounds[1])
        .fold(f64::NEG_INFINITY, f64::max);
    let right = boards
        .iter()
        .map(|b| b.bounds[2])
        .fold(f64::NEG_INFINITY, f64::max);
    let bottom = boards
        .iter()
        .map(|b| b.bounds[3])
        .fold(f64::INFINITY, f64::min);
    let canvas = crate::vector_canvas::Canvas {
        origin_px: [0.0; 2],
        size_px: [right - left, top - bottom],
        unit: crate::dimensions::Unit::Pt,
        process_space: Default::default(),
    };
    let dimensions = canvas.dimensions()?;
    let placement = [1.0, 0.0, 0.0, -1.0, -left, top];
    let mut items = Vec::new();
    for (n, board) in boards.iter().enumerate() {
        let size = [
            board.bounds[2] - board.bounds[0],
            board.bounds[1] - board.bounds[3],
        ];
        let c = crate::vector_canvas::Canvas {
            size_px: size,
            ..canvas
        };
        let dims = c.dimensions()?;
        items.push(json!({"id":format!("board-{n}"),"name":board.name,"locked":board.locked,"transform":[1,0,0,1,board.bounds[0]-left,top-board.bounds[1]],
            "content":{"type":"frame","frame":{"role":"artboard","scope":"scene","width":dims[0],"height":dims[1],"logical_size":size}}}));
    }
    let mut state = State {
        items,
        layer: None,
        target: None,
        paths: 0,
        layers: 0,
        commands: vec![],
        start: None,
        fill: None,
        visible: true,
        locked: false,
        opacity: 1.0,
        placement,
        profile,
    };
    let tokens = tokens::lex(&data[body..end], control)?;
    let mut operands = Vec::new();
    let mut metadata = Vec::new();
    for token in tokens {
        control.check()?;
        if let Token::Comment(comment) = &token
            && let Some(comment) = comment.strip_prefix(b"_")
        {
            metadata.extend_from_slice(comment);
            metadata.push(b'\n');
            continue;
        }
        if !metadata.is_empty() {
            state.metadata(&metadata, control)?;
            metadata.clear();
        }
        match token {
            Token::Comment(comment) => {
                if ![b"AI5_BeginLayer".as_slice(), b"AI5_EndLayer--"].contains(&comment.as_slice())
                {
                    return Err(unsupported("Unknown semantic comment in native artwork"));
                }
                if !operands.is_empty() {
                    return Err(invalid("Native comment splits an operand list"));
                }
            }
            Token::Word(ref name) if name.parse::<f64>().is_err() => {
                state.operator(name, &operands)?;
                operands.clear();
            }
            v => {
                operands.push(v);
                if operands.len() > 32 {
                    return Err(limit("Native operator operand budget exceeded"));
                }
            }
        }
    }
    if !metadata.is_empty() {
        state.metadata(&metadata, control)?;
    }
    if !operands.is_empty()
        || state.layer.is_some()
        || !state.commands.is_empty()
        || state.layers as f64 != expected_layers
    {
        return Err(invalid("Incomplete native layer or path structure"));
    }
    let trailer = tokens::lex(&data[tail..], control)?;
    let expected = tokens::lex(
        b"gsave annotatepage grestore showpage\n%%Trailer\n%%EOF",
        control,
    )?;
    if trailer != expected {
        return Err(unsupported("Unsupported native page trailer"));
    }
    let mapping: Vec<_> = state
        .items
        .iter()
        .map(|v| json!({"item_id":v["id"],"source_name":v["name"]}))
        .collect();
    let document:Document=serde_json::from_value(json!({"schema_version":2,"id":id,"kind":"vector","color_space":"srgb","width":dimensions[0],"height":dimensions[1],"resolution_ppi":72,"vector_canvas":canvas,"resource_profile":profile,"items":state.items})).map_err(|_|invalid("Native artwork cannot be represented by the document model"))?;
    crate::model::validate_controlled(&document, control)?;
    if serde_json::to_vec(&document)
        .map_err(|_| invalid("Cannot encode native document"))?
        .len()
        > profile.bytes()
    {
        return Err(limit("Imported native document exceeds snapshot budget"));
    }
    Ok(
        json!({"document":document,"mapping":{"source_to_document":placement,"items":mapping},"counts":{"artboards":boards.len(),"layers":state.layers,"paths":state.paths}}),
    )
}
struct State {
    items: Vec<Value>,
    layer: Option<usize>,
    target: Option<usize>,
    layers: usize,
    paths: usize,
    commands: Vec<Value>,
    start: Option<[f64; 2]>,
    fill: Option<[u8; 4]>,
    visible: bool,
    locked: bool,
    opacity: f64,
    placement: [f64; 6],
    profile: ResourceProfile,
}
fn values(operands: &[Token], count: usize) -> Result<Vec<f64>, Error> {
    if operands.len() != count {
        return Err(invalid("Wrong native operator operand count"));
    }
    operands.iter().map(Token::number).collect()
}
impl State {
    fn operator(&mut self, name: &str, args: &[Token]) -> Result<(), Error> {
        if self.items.len() > self.profile.items() {
            return Err(limit("Native artwork item budget exceeded"));
        }
        match name {
            "Lb" => {
                if self.layer.is_some() || !self.commands.is_empty() {
                    return Err(unsupported("Nested native layers are not yet supported"));
                }
                let v = values(args, 14)?;
                if ![0.0, 1.0].contains(&v[0])
                    || ![0.0, 1.0].contains(&v[2])
                    || v[1] != 1.0
                    || v[3..7] != [1.0, 0.0, 0.0, v[0]]
                    || v[11..] != [0.0, 50.0, 0.0]
                {
                    return Err(unsupported("Unsupported native layer flags"));
                }
                if v[7].fract() != 0.0
                    || v[7] < 0.0
                    || v[8..11].iter().any(|x| !(0.0..=255.0).contains(x))
                {
                    return Err(invalid("Invalid native layer presentation values"));
                }
                let n = self.items.len();
                self.items.push(json!({"id":format!("layer-{}",self.layers),"name":"","visible":v[0]==1.0,"locked":v[2]==0.0,"transform":self.placement,"content":{"type":"group","role":"layer"}}));
                self.layers += 1;
                self.layer = Some(n);
                self.target = Some(n);
                self.fill = None;
                self.opacity = 1.0;
                self.visible = true;
                self.locked = false;
            }
            "LB" => {
                values(args, 0)?;
                if self.layer.take().is_none() || !self.commands.is_empty() {
                    return Err(invalid("Incomplete native layer"));
                }
                self.target = None;
            }
            "Ln" => {
                if args.len() != 1 {
                    return Err(invalid("Invalid native layer name"));
                }
                let i = self
                    .layer
                    .ok_or_else(|| invalid("Native layer name outside a layer"))?;
                self.items[i]["name"] = json!(args[0].text()?);
            }
            "AE" | "O" | "XR" => {
                if values(args, 1)? != [0.0] {
                    return Err(unsupported("Unsupported native appearance or winding flag"));
                }
            }
            "As" => {
                if values(args, 1)? != [4.0] {
                    return Err(unsupported("Unsupported native appearance boundary"));
                }
            }
            "A" | "Xw" => {
                let v = values(args, 1)?[0];
                if v != 0.0 && v != 1.0 {
                    return Err(invalid("Invalid native object flag"));
                }
                if name == "A" {
                    self.locked = v == 1.0;
                } else {
                    self.visible = v == 0.0;
                }
            }
            "Xy" => {
                let v = values(args, 5)?;
                if v[0] != 0.0 || v[2..] != [0.0; 3] || !(0.0..=1.0).contains(&v[1]) {
                    return Err(unsupported(
                        "Unsupported native blending or opacity controls",
                    ));
                }
                self.opacity = v[1];
            }
            "Xa" => {
                let v = values(args, 7)?;
                if v.iter().any(|v| !(0.0..=1.0).contains(v)) {
                    return Err(invalid("Native color outside its declared range"));
                }
                let mut color = [0, 0, 0, 255];
                for (i, v) in v[4..].iter().enumerate() {
                    let n = v * 255.0;
                    if (n - n.round()).abs() > 1e-8 {
                        return Err(unsupported(
                            "Native fractional RGB components need a retained precision mapping",
                        ));
                    }
                    color[i] = n.round() as u8;
                }
                self.fill = Some(color);
            }
            "J" | "j" => {
                let v = values(args, 1)?[0];
                if ![0.0, 1.0, 2.0].contains(&v) {
                    return Err(invalid("Invalid native cap or join"));
                }
            }
            "w" | "M" => {
                if values(args, 1)?[0] < 0.0 {
                    return Err(invalid("Invalid native line control"));
                }
            }
            "d" => {
                if args
                    != [
                        Token::Mark(b'['),
                        Token::Mark(b']'),
                        Token::Word("0".into()),
                    ]
                {
                    return Err(unsupported("Native dash controls have not been mapped"));
                }
            }
            "m" => {
                let p = values(args, 2)?;
                if !self.commands.is_empty() {
                    return Err(unsupported("Native compound paths have not been mapped"));
                }
                self.start = Some([p[0], p[1]]);
                self.commands.push(json!({"verb":"move","to":p}));
            }
            "L" => {
                let p = values(args, 2)?;
                self.path()?;
                self.commands.push(json!({"verb":"line","to":p}));
            }
            "C" => {
                let p = values(args, 6)?;
                self.path()?;
                self.commands
                    .push(json!({"verb":"cubic","control1":p[..2],"control2":p[2..4],"to":p[4..]}));
            }
            "f" => {
                values(args, 0)?;
                self.path()?;
                let layer = self
                    .layer
                    .ok_or_else(|| invalid("Native path outside a layer"))?;
                let fill = self
                    .fill
                    .ok_or_else(|| unsupported("Native fill requires explicit RGB color"))?;
                if self
                    .commands
                    .last()
                    .is_some_and(|c| c["verb"] == "line" && c["to"] == json!(self.start.unwrap()))
                {
                    self.commands.pop();
                }
                self.commands.push(json!({"verb":"close"}));
                let commands = std::mem::take(&mut self.commands);
                self.start = None;
                let parent = self.items[layer]["id"].clone();
                self.target = Some(self.items.len());
                self.items.push(json!({"id":format!("path-{}",self.paths),"name":"","parent":parent,"visible":self.visible,"locked":self.locked,"opacity":self.opacity,"content":{"type":"vector","geometry":{"shape":"path","commands":commands},"fill":fill}}));
                self.paths += 1;
            }
            _ => {
                return Err(unsupported(&format!(
                    "Unsupported native artwork operator: {name}"
                )));
            }
        }
        if self.commands.len() > crate::model::MAX_SEGMENTS {
            return Err(limit("Native path command budget exceeded"));
        }
        Ok(())
    }
    fn path(&self) -> Result<(), Error> {
        if self.start.is_none() {
            Err(invalid("Native path has no initial point"))
        } else {
            Ok(())
        }
    }
    fn metadata(&mut self, bytes: &[u8], control: &Control) -> Result<(), Error> {
        let target = self
            .target
            .ok_or_else(|| invalid("Native object metadata has no object"))?;
        let t = tokens::lex(bytes, control)?;
        if t.len() < 3
            || t[0] != Token::Name("ArtDictionary".into())
            || tokens::end(&t, 0)? != t.len() - 1
        {
            return Err(unsupported("Unsupported native object metadata container"));
        }
        let mut at = 2;
        let mut keys = std::collections::BTreeSet::new();
        while at < t.len() - 1 {
            if t[at] == Token::Name("XMLUID".into()) {
                if t.get(at + 1) != Some(&Token::Mark(b':'))
                    || t.get(at + 3) != Some(&Token::Mark(b';'))
                    || t.get(at + 4) != Some(&Token::Bytes(b"AI10_ArtUID".to_vec()))
                    || t.get(at + 5) != Some(&Token::Mark(b','))
                    || !keys.insert("name".to_owned())
                {
                    return Err(invalid("Invalid native object identity metadata"));
                }
                let name = t[at + 2].text()?;
                // A layer's separate data identity is not its display label.
                if Some(target) != self.layer {
                    self.items[target]["name"] = json!(names::decode(&name)?);
                }
                at += 6;
            } else {
                let value = t
                    .get(at)
                    .ok_or_else(|| invalid("Missing native metadata value"))?
                    .number()?;
                let key = t
                    .get(at + 2)
                    .ok_or_else(|| invalid("Missing native metadata key"))?
                    .text()?;
                if Some(target) != self.layer
                    || value != 1.0
                    || t.get(at + 1) != Some(&Token::Name("Bool".into()))
                    || t.get(at + 3) != Some(&Token::Mark(b','))
                    || ![
                        "AISFW Export Layer To CSS",
                        "AISFW Export Layer Visible To CSS",
                    ]
                    .contains(&key.as_str())
                    || !keys.insert(key)
                {
                    return Err(unsupported("Unmapped native object or layer metadata"));
                }
                at += 4;
            }
        }
        Ok(())
    }
}
