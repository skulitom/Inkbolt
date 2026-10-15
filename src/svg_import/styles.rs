//! Bounded author cascade over the public CSS tokenizer; source numbers stay f64 lexemes.
use super::*;
use crate::limits::svg_import::{
    MAX_CSS_DECLARATIONS, MAX_CSS_MATCH_WORK, MAX_CSS_RULES, MAX_CSS_SELECTOR_COMPONENTS,
};
use cssparser::{ParseErrorKind, Parser, Token};
use std::cell::Cell;

type Properties<'a> = BTreeMap<&'a str, &'a str>;
type Specificity = (usize, usize, usize);

#[derive(Default)]
struct Selector {
    tag: Option<String>,
    ids: Vec<String>,
    classes: Vec<String>,
    components: usize,
}
impl Selector {
    fn specificity(&self) -> Specificity {
        (
            self.ids.len(),
            self.classes.len(),
            usize::from(self.tag.is_some()),
        )
    }
    fn matches(&self, node: Node<'_, '_>, classes: &HashSet<&str>) -> bool {
        self.tag
            .as_ref()
            .is_none_or(|tag| tag == node.tag_name().name())
            && self
                .ids
                .iter()
                .all(|id| node.attribute("id") == Some(id.as_str()))
            && self
                .classes
                .iter()
                .all(|class| classes.contains(class.as_str()))
    }
    fn work(&self) -> usize {
        1 + self.tag.as_ref().map_or(0, String::len)
            + self
                .ids
                .iter()
                .chain(&self.classes)
                .map(|s| 1 + s.len())
                .sum::<usize>()
    }
}
struct Declaration {
    name: String,
    value: String,
}
struct Rule {
    selectors: Vec<Selector>,
    declarations: Vec<Declaration>,
}
pub(super) struct Sheet {
    pub(super) omitted_ids: HashSet<String>,
    rules: Vec<Rule>,
    inline: BTreeMap<usize, Vec<Declaration>>,
    declaration_count: usize,
    work: Cell<usize>,
    control: crate::control::Control,
}

fn located(mut error: Error, node: Node<'_, '_>, context: &str) -> Error {
    let pos = node.document().text_pos_at(node.range().start);
    let details = error.details.get_or_insert_with(|| Box::new(json!({})));
    details["element"] = json!(node.tag_name().name());
    details["byte_offset"] = json!(node.range().start);
    details["line"] = json!(pos.row);
    details["column"] = json!(pos.col);
    details["context"] = json!(context);
    error
}
fn syntax(parser: &Parser<'_>, message: &str) -> Error {
    let mut error = unsupported(message);
    error.details = Some(Box::new(
        json!({"css_byte_offset":parser.position().byte_index()}),
    ));
    error
}
fn nested<T>(
    parser: &mut Parser<'_>,
    f: impl FnOnce(&mut Parser<'_>) -> Result<T, Error>,
) -> Result<T, Error> {
    parser
        .parse_nested_block(|inner| f(inner).map_err(cssparser::ParseError::custom))
        .map_err(|e| match e.kind {
            ParseErrorKind::Custom(error) => error,
            ParseErrorKind::Basic(_) => syntax(parser, "Malformed CSS block"),
        })
}
// Keep comments distinct from whitespace: a comment alone is not a descendant
// combinator. Never deserialize numeric token values (the tokenizer uses f32).
fn next<'a>(parser: &mut Parser<'a>) -> Result<Option<(Token<'a>, &'a str)>, Error> {
    loop {
        let start = parser.position();
        let Ok(token) = parser.next_including_whitespace_and_comments().cloned() else {
            return Ok(None);
        };
        let raw = parser.slice_from(start);
        if matches!(token, Token::Comment(_)) {
            if !raw.ends_with("*/") {
                return Err(syntax(parser, "Unclosed CSS comment"));
            }
            continue;
        }
        if raw.contains('\\') || raw.contains('\0') {
            return Err(syntax(
                parser,
                "CSS escapes and NUL characters are not supported",
            ));
        }
        if token.is_parse_error() {
            return Err(syntax(parser, "Malformed CSS token"));
        }
        return Ok(Some((token, raw)));
    }
}

impl Sheet {
    pub fn parse(root: Node<'_, '_>, control: &crate::control::Control) -> Result<Self, Error> {
        let mut sheet = Self {
            omitted_ids: HashSet::new(),
            rules: vec![],
            inline: BTreeMap::new(),
            declaration_count: 0,
            work: Cell::new(0),
            control: control.clone(),
        };
        for node in root.descendants().filter(Node::is_element) {
            control.check()?;
            if node.tag_name().name() == "style" {
                let result = (|| {
                    for attr in node.attributes() {
                        if attr.namespace().is_some() || !["id", "type"].contains(&attr.name()) {
                            return Err(unsupported(
                                "Style elements accept only id and type; media and alternate stylesheets are unsupported",
                            ));
                        }
                    }
                    if node
                        .attribute("type")
                        .is_some_and(|s| !s.trim().eq_ignore_ascii_case("text/css"))
                    {
                        return Err(unsupported("Style elements require text/css"));
                    }
                    if node.children().any(|n| n.is_element()) {
                        return Err(unsupported("Style elements require CSS text or CDATA"));
                    }
                    let source = node
                        .children()
                        .filter(Node::is_text)
                        .filter_map(|n| n.text())
                        .collect::<String>();
                    sheet.rules(&mut Parser::new(&source))
                })();
                result.map_err(|e| located(e, node, "stylesheet"))?;
            }
            if let Some(source) = node.attribute("style") {
                let declarations = sheet
                    .declarations(&mut Parser::new(source))
                    .map_err(|e| located(e, node, "inline_style"))?;
                sheet.inline.insert(node.range().start, declarations);
            }
        }
        Ok(sheet)
    }
    fn rules(&mut self, parser: &mut Parser<'_>) -> Result<(), Error> {
        loop {
            self.control.check()?;
            let mut selectors = Vec::new();
            let mut selector = Selector::default();
            let mut separated = false;
            let mut class_next = false;
            loop {
                let Some((token, _)) = next(parser)? else {
                    if selector.components == 0 && selectors.is_empty() {
                        return Ok(());
                    }
                    return Err(syntax(parser, "CSS rule requires a declaration block"));
                };
                match token {
                    Token::WhiteSpace(_) => {
                        separated |= selector.components > 0 || class_next;
                        continue;
                    }
                    Token::Comma | Token::CurlyBracketBlock => {
                        if selector.components == 0 || class_next {
                            return Err(syntax(parser, "Empty or incomplete CSS selector"));
                        }
                        selectors.push(selector);
                        if matches!(token, Token::CurlyBracketBlock) {
                            break;
                        }
                        selector = Selector::default();
                        separated = false;
                        continue;
                    }
                    _ if separated => {
                        return Err(syntax(parser, "CSS descendant selectors are not supported"));
                    }
                    Token::Ident(name) if class_next => {
                        selector.classes.push(name.to_string());
                        class_next = false;
                    }
                    Token::Ident(name) if selector.components == 0 => {
                        selector.tag = Some(name.to_string());
                    }
                    Token::Delim('*') if selector.components == 0 => {}
                    Token::IDHash(name) if !class_next => selector.ids.push(name.to_string()),
                    Token::Delim('.') if !class_next => {
                        class_next = true;
                        continue;
                    }
                    _ => {
                        return Err(syntax(
                            parser,
                            "Only type, universal, class, ID and simple compound CSS selectors are supported",
                        ));
                    }
                }
                selector.components += 1;
                if selector.components > MAX_CSS_SELECTOR_COMPONENTS
                    || selectors.len() >= MAX_CSS_RULES
                {
                    return Err(Error::new(
                        "RESOURCE_LIMIT",
                        "SVG CSS selector budget exceeded",
                    ));
                }
            }
            if self.rules.len() >= MAX_CSS_RULES {
                return Err(Error::new("RESOURCE_LIMIT", "SVG CSS rule limit exceeded"));
            }
            let block_start = parser.position();
            let declarations = nested(parser, |inner| self.declarations(inner))?;
            if !parser.slice_from(block_start).ends_with('}') {
                return Err(syntax(parser, "Unclosed CSS rule"));
            }
            self.rules.push(Rule {
                selectors,
                declarations,
            });
        }
    }
    fn declarations(&mut self, parser: &mut Parser<'_>) -> Result<Vec<Declaration>, Error> {
        let mut declarations = Vec::new();
        while let Some((token, _)) = next(parser)? {
            self.control.check()?;
            let name = match token {
                Token::WhiteSpace(_) | Token::Semicolon => continue,
                Token::Ident(name) => name.to_ascii_lowercase(),
                _ => {
                    return Err(syntax(
                        parser,
                        "Expected a CSS property name; at-rules are unsupported",
                    ));
                }
            };
            loop {
                match next(parser)? {
                    Some((Token::WhiteSpace(_), _)) => continue,
                    Some((Token::Colon, _)) => break,
                    _ => return Err(syntax(parser, "CSS declaration requires a colon")),
                }
            }
            if !(PROPERTIES.contains(&name.as_str()) || labels::PROPERTIES.contains(&name.as_str()))
            {
                return Err(syntax(parser, "Unsupported CSS property"));
            }
            let value = self.value(parser, false, &name)?;
            if value.is_empty() {
                return Err(syntax(parser, "Empty CSS property value"));
            }
            // Validate even unmatched/overridden declarations rather than dropping
            // unsupported semantics through CSS error recovery.
            validate_declaration(&name, &value).map_err(|mut e| {
                e.details = Some(Box::new(
                    json!({"css_byte_offset":parser.position().byte_index()}),
                ));
                e
            })?;
            self.declaration_count += 1;
            if self.declaration_count > MAX_CSS_DECLARATIONS {
                return Err(Error::new(
                    "RESOURCE_LIMIT",
                    "SVG CSS declaration limit exceeded",
                ));
            }
            declarations.push(Declaration { name, value });
        }
        Ok(declarations)
    }
    fn value(
        &self,
        parser: &mut Parser<'_>,
        in_function: bool,
        property: &str,
    ) -> Result<String, Error> {
        let mut parts = Vec::new();
        let mut previous_number = false;
        while let Some((token, raw)) = next(parser)? {
            self.control.check()?;
            if matches!(token, Token::WhiteSpace(_)) {
                continue;
            }
            if property == "font-family"
                && !matches!(
                    token,
                    Token::Ident(_) | Token::QuotedString(_) | Token::Comma | Token::Semicolon
                )
            {
                return Err(syntax(
                    parser,
                    "CSS font families require identifiers or quoted strings",
                ));
            }
            // The older SVG length parser tolerates whitespace before units.
            // A CSS number followed by an identifier is two tokens, never a dimension.
            if previous_number && matches!(token, Token::Ident(_)) {
                return Err(syntax(
                    parser,
                    "A CSS number and unit must form one dimension token",
                ));
            }
            previous_number = matches!(token, Token::Number { .. });
            match token {
                Token::Semicolon if !in_function => break,
                Token::Function(ref name)
                    if !in_function && ["rgb", "url"].contains(&name.as_ref()) =>
                {
                    let start = parser.position();
                    let value = nested(parser, |inner| self.value(inner, true, property))?;
                    if !parser.slice_from(start).ends_with(')') {
                        return Err(syntax(parser, "Unclosed CSS function"));
                    }
                    parts.push(format!("{name}({value})"));
                }
                Token::QuotedString(_)
                    if !raw.ends_with(raw.chars().next().unwrap()) || raw.len() < 2 =>
                {
                    return Err(syntax(parser, "Unclosed CSS string"));
                }
                Token::UnquotedUrl(_) if !raw.ends_with(')') => {
                    return Err(syntax(parser, "Unclosed CSS URL"));
                }
                Token::Ident(_)
                | Token::Hash(_)
                | Token::IDHash(_)
                | Token::QuotedString(_)
                | Token::UnquotedUrl(_)
                | Token::Number { .. }
                | Token::Percentage { .. }
                | Token::Dimension { .. }
                | Token::Comma => parts.push(raw.to_owned()),
                _ => {
                    return Err(syntax(
                        parser,
                        "Unsupported CSS value syntax; !important, at-rules and nested functions are unsupported",
                    ));
                }
            }
        }
        if property == "font-family"
            && parts.len() > 1
            && parts.iter().any(|part| {
                ["inherit", "initial", "unset", "revert", "revert-layer"]
                    .contains(&part.to_ascii_lowercase().as_str())
            })
        {
            return Err(syntax(
                parser,
                "CSS-wide keywords cannot be unquoted font family names",
            ));
        }
        let value = parts.join(" ");
        Ok(if value.eq_ignore_ascii_case("inherit") {
            "inherit".into()
        } else {
            value
        })
    }
    fn charge(&self, amount: usize) -> Result<(), Error> {
        self.control.check()?;
        let work = self.work.get().saturating_add(amount);
        if work > MAX_CSS_MATCH_WORK {
            return Err(Error::new(
                "RESOURCE_LIMIT",
                "SVG CSS matching work limit exceeded",
            ));
        }
        self.work.set(work);
        Ok(())
    }
    pub fn apply<'a>(
        &'a self,
        node: Node<'_, '_>,
        properties: &mut Properties<'a>,
    ) -> Result<(), Error> {
        let classes: HashSet<_> = node
            .attribute("class")
            .unwrap_or("")
            .split_ascii_whitespace()
            .collect();
        let mut priorities = BTreeMap::new();
        for rule in &self.rules {
            let mut best = None;
            for selector in &rule.selectors {
                self.charge(selector.work())
                    .map_err(|e| located(e, node, "selector_matching"))?;
                if selector.matches(node, &classes) {
                    best = Some(best.map_or(selector.specificity(), |s: Specificity| {
                        s.max(selector.specificity())
                    }));
                }
            }
            if let Some(specificity) = best {
                self.charge(rule.declarations.len())?;
                for declaration in &rule.declarations {
                    apply_declaration(properties, &mut priorities, declaration, (1, specificity));
                }
            }
        }
        if let Some(declarations) = self.inline.get(&node.range().start) {
            self.charge(declarations.len())?;
            for declaration in declarations {
                apply_declaration(properties, &mut priorities, declaration, (2, (0, 0, 0)));
            }
        }
        Ok(())
    }
}
fn validate_declaration(name: &str, value: &str) -> Result<(), Error> {
    if ["initial", "unset", "revert", "revert-layer"].contains(&value.to_ascii_lowercase().as_str())
    {
        return Err(unsupported(
            "CSS-wide keywords other than inherit are not supported",
        ));
    }
    if name == "font-size"
        && let Some(relative) = value.strip_suffix("em").or_else(|| value.strip_suffix('%'))
    {
        if number(relative)? <= 0.0 {
            return Err(unsupported("Relative font size must be positive"));
        }
        // Its range depends on the real inherited size, not a synthetic parent.
        return Ok(());
    }
    styled(&Style::default(), &BTreeMap::from([(name, value)]))?;
    Ok(())
}
fn apply_declaration<'a>(
    properties: &mut Properties<'a>,
    priorities: &mut BTreeMap<&'a str, (u8, Specificity)>,
    declaration: &'a Declaration,
    priority: (u8, Specificity),
) {
    let mut set = |key: &'a str, value: &'a str| {
        if priorities.get(key).is_none_or(|p| *p <= priority) {
            properties.insert(key, value);
            priorities.insert(key, priority);
        }
    };
    set(&declaration.name, &declaration.value);
    if declaration.name == "mask" {
        set(
            "mask-mode",
            if declaration.value == "inherit" {
                "inherit"
            } else {
                "match-source"
            },
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cancellation_after_parsing_stops_stylesheet_matching() {
        let xml =
            roxmltree::Document::parse("<svg><style>.a{fill:red}</style><rect class='a'/></svg>")
                .unwrap();
        let control = crate::control::Control::default();
        let sheet = Sheet::parse(xml.root_element(), &control).unwrap();
        let rect = xml.descendants().find(|n| n.has_tag_name("rect")).unwrap();
        control.cancel();
        assert_eq!(
            sheet.apply(rect, &mut BTreeMap::new()).unwrap_err().code,
            "CANCELLED"
        );
    }
}
