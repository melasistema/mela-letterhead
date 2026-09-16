// ═══════════════════════════════════════════════════════════════════════════
//  mela-letterhead · letterhead.typ
//
//  A letterhead with no brand, no language and no document in it. Everything
//  that could identify any of the three arrives in `document.json`, which the
//  tool writes into this file's directory before compiling. Nothing here needs
//  editing to print somebody else's paper.
//
//  Two conventions make that possible:
//
//    · Lengths in the JSON are plain numbers of typographic points, because
//      JSON has no length type. `len` turns them back into lengths.
//    · Language has already been resolved: every string is in the document's
//      language by the time it reaches this file.
//
//  Page composition:
//
//    · first page  → the full header band: logo and fields
//    · inner pages → a running header: small logo, title, page n of N
//    · last page   → the full footer band: columns of legal and contact detail
//
//  The footer is the awkward one. It sits on the last page only, but Typst
//  fixes the bottom margin for the whole document, so the room it needs is
//  reserved by a block at the end of the body instead — `page.footer_reserve`,
//  computed by the tool. A footer on every page reserves margin as usual.
// ═══════════════════════════════════════════════════════════════════════════

// ─── JSON to Typst ─────────────────────────────────────────────────────────

#let len(value) = if value == none { 0pt } else { float(value) * 1pt }

#let em-of(value) = if value == none { 0em } else { float(value) * 1em }

#let alignment-of(name) = {
  if name == "left" { left } else if name == "right" { right } else { center }
}

// ─── The brand mark ────────────────────────────────────────────────────────
// A brand without a logo file still has a name, and a name set in the display
// face is a perfectly good letterhead. It occupies exactly the width the logo
// would have, so the fields beside it stay where they are: the name is set at
// a size proportional to that width, then measured, and shrunk to fit if it
// came out wider. "Ann Lee" keeps the nominal size; "Northbridge Surveying and
// Associates" is scaled down until it stops running into the fields.

#let brand-mark(cfg, width) = {
  let logo = cfg.brand.at("logo", default: none)
  if logo != none {
    image(logo, width: width)
  } else {
    let name = cfg.brand.name
    let nominal = width * 0.17
    let styled(size) = text(
      font: cfg.fonts.display,
      weight: 700,
      size: size,
      fill: rgb(cfg.palette.ink),
      tracking: width * 0.002,
    )[#name]

    context {
      let natural = measure(styled(nominal)).width
      styled(if natural > width { nominal * (width / natural) } else { nominal })
    }
  }
}

// ─── Header band (first page) ──────────────────────────────────────────────

// A field with no value is not a field with nothing after it: on a form it is
// a line to fill in by hand. Which of the two it becomes is `when_empty`.
#let header-field(field, cfg) = {
  let f = cfg.header.fields
  let label = field.at("label", default: none)
  let value = field.at("value", default: none)

  if label != none {
    text(font: cfg.fonts.sans, weight: 700, size: len(f.size))[#label]
    h(len(f.label_gap))
  }
  if value != none {
    text(font: cfg.fonts.sans, weight: 400, size: len(f.size))[#value]
  } else if f.when_empty == "rule" {
    box(
      width: len(f.blank_width),
      baseline: 2.5pt,
      line(length: 100%, stroke: 0.5pt + rgb(cfg.palette.muted)),
    )
  }
}

#let header-band(cfg) = {
  let pal = cfg.palette
  let page-width = len(cfg.page.width)
  let side = len(cfg.page.margin.x)
  let column = page-width - 2 * side
  let height = len(cfg.header.height)

  place(top + left, rect(
    width: page-width,
    height: height,
    fill: rgb(pal.band),
    stroke: none,
  ))

  let rule = len(cfg.header.rule)
  if rule > 0pt {
    place(top + left, dy: height - rule / 2, rect(
      width: page-width,
      height: rule,
      fill: rgb(pal.rule),
      stroke: none,
    ))
  }

  place(
    top + left,
    dx: side,
    dy: len(cfg.header.logo.y),
    brand-mark(cfg, len(cfg.header.logo.width)),
  )

  let fields = cfg.header.fields.items
  if fields.len() > 0 {
    place(top + left, dx: side, dy: len(cfg.header.fields.y), box(
      width: column,
      align(alignment-of(cfg.header.fields.align), {
        set par(leading: len(cfg.header.fields.leading), justify: false)
        for (index, field) in fields.enumerate() {
          header-field(field, cfg)
          if index + 1 < fields.len() { linebreak() }
        }
      }),
    ))
  }
}

// ─── Running header (every page after the first) ───────────────────────────

#let running-header(cfg, current, total) = {
  let r = cfg.running
  let side = len(cfg.page.margin.x)
  let column = len(cfg.page.width) - 2 * side

  // The page numbers are the one thing the tool cannot resolve in advance.
  let label = r.text.replace("{page}", str(current)).replace("{pages}", str(total))

  place(
    top + left,
    dx: side,
    dy: len(r.logo_y),
    brand-mark(cfg, len(r.logo_width)),
  )

  place(top + left, dx: side, dy: len(r.text_y), box(
    width: column,
    align(
      alignment-of(r.align),
      text(
        font: cfg.fonts.sans,
        size: len(r.size),
        fill: rgb(cfg.palette.muted),
        tracking: len(r.tracking),
      )[#label],
    ),
  ))

  let rule = len(r.rule)
  if rule > 0pt {
    place(top + left, dx: side, dy: len(r.rule_y), line(
      length: column,
      stroke: rule + rgb(cfg.palette.hairline),
    ))
  }
}

// ─── Footer band (last page, or every page) ────────────────────────────────

#let footer-row(row, cfg) = {
  let pal = cfg.palette
  let label = row.at("label", default: none)
  let value = row.at("value", default: none)
  let target = row.at("link", default: none)
  let style = row.at("style", default: "normal")

  let ink = if style == "highlight" {
    rgb(pal.highlight)
  } else if style == "muted" {
    rgb(pal.muted)
  } else {
    rgb(pal.ink)
  }

  if label != none {
    text(weight: 700)[#label]
    h(0.3em)
  }
  if value != none {
    let body = text(fill: ink)[#value]
    if target != none {
      link(target, underline(offset: 1.6pt, body))
    } else {
      body
    }
  }
}

#let footer-column(column, cfg) = {
  let f = cfg.footer
  set par(leading: len(f.leading), spacing: len(f.leading), justify: false)
  set text(font: cfg.fonts.display, size: len(f.size), fill: rgb(cfg.palette.ink))

  align(alignment-of(f.align), {
    let title = column.at("title", default: none)
    if title != none {
      text(weight: 700, size: len(f.title_size))[#title]
      v(len(f.title_gap))
    }
    let rows = column.at("rows", default: ())
    for (index, row) in rows.enumerate() {
      footer-row(row, cfg)
      if index + 1 < rows.len() { linebreak() }
    }
  })
}

#let footer-band(cfg) = {
  let f = cfg.footer
  let pal = cfg.palette
  let page-width = len(cfg.page.width)
  let side = len(cfg.page.margin.x)
  let offset = len(f.offset)
  let height = len(f.height)

  place(bottom + left, dy: -offset, rect(
    width: page-width,
    height: height,
    fill: rgb(pal.band),
    stroke: none,
  ))

  let rule = len(f.rule)
  if rule > 0pt {
    place(bottom + left, dy: -(offset + height - rule / 2), rect(
      width: page-width,
      height: rule,
      fill: rgb(pal.rule),
      stroke: none,
    ))
  }

  let columns = f.columns
  let body = box(width: page-width - 2 * side, grid(
    columns: (1fr,) * columns.len(),
    column-gutter: len(f.gutter),
    // Top, so that the column titles line up across the band even when one
    // column runs to more lines than its neighbour.
    align: top,
    ..columns.map(column => footer-column(column, cfg)),
  ))

  // Centre the block in the band's own height rather than at a fixed offset,
  // so a column may gain or lose a row without anything being re-measured.
  context {
    let slack = (height - measure(body).height) / 2
    place(bottom + left, dx: side, dy: -(offset + slack), body)
  }
}

// ─── The document ──────────────────────────────────────────────────────────

#let letterhead(cfg, body) = {
  let pal = cfg.palette
  let type = cfg.typography
  let accent = rgb(pal.accent)
  let hairline = rgb(pal.hairline)

  set document(title: cfg.document.title, author: cfg.document.author)

  set page(
    width: len(cfg.page.width),
    height: len(cfg.page.height),
    margin: (
      left: len(cfg.page.margin.x),
      right: len(cfg.page.margin.x),
      top: len(cfg.page.margin.top),
      bottom: len(cfg.page.margin.bottom),
    ),
    background: context {
      let current = counter(page).at(here()).first()
      let total = counter(page).final().first()

      if current == 1 and cfg.header.show {
        header-band(cfg)
      } else if cfg.running.show {
        running-header(cfg, current, total)
      }

      if cfg.footer.show and (cfg.footer.pages == "all" or current == total) {
        footer-band(cfg)
      }
    },
  )

  // ─── Body text ───────────────────────────────────────────────────────────
  set text(
    font: cfg.fonts.serif,
    size: len(type.size),
    fill: rgb(pal.ink),
    lang: cfg.document.lang,
    region: cfg.document.at("region", default: none),
    hyphenate: type.hyphenate,
  )
  set par(
    justify: type.justify,
    leading: em-of(type.leading),
    spacing: em-of(type.paragraph_spacing),
    linebreaks: "optimized",
  )

  // ─── Headings ────────────────────────────────────────────────────────────
  // A heading is never justified: a two-word line stretched across the column
  // is the surest sign of a document nobody typeset.
  show heading: set par(justify: false, leading: 0.52em)

  show heading.where(level: 1): it => block(width: 100%, above: 0pt, below: 1.5em, {
    set text(font: cfg.fonts.sans, size: len(type.headings.h1), weight: 700)
    it.body
    v(0.55em)
    line(length: 100%, stroke: 1.2pt + accent.lighten(45%))
  })

  show heading.where(level: 2): it => block(
    width: 100%,
    above: 1.9em,
    below: 0.9em,
    breakable: false,
    {
      line(length: 100%, stroke: 0.6pt + hairline)
      v(0.62em)
      set text(font: cfg.fonts.sans, size: len(type.headings.h2), weight: 700)
      it.body
    },
  )

  show heading.where(level: 3): it => block(
    width: 100%,
    above: 1.55em,
    below: 0.6em,
    breakable: false,
    {
      set text(
        font: cfg.fonts.sans,
        size: len(type.headings.h3),
        weight: 700,
        fill: accent.darken(25%),
      )
      it.body
    },
  )

  show heading.where(level: 4): it => block(width: 100%, above: 1.3em, below: 0.5em, {
    set text(font: cfg.fonts.sans, size: len(type.headings.h4), weight: 700)
    it.body
  })

  // ─── Tables ──────────────────────────────────────────────────────────────
  set table(
    inset: (x: 6pt, y: 5.2pt),
    stroke: (_, _) => (bottom: 0.4pt + hairline),
  )
  // Pandoc emits an explicit hline under a header row; this is its weight.
  set table.hline(stroke: 0.7pt + rgb(pal.muted))
  show table: set text(size: len(type.table_size))
  show table: set par(justify: false, leading: 0.62em, spacing: 0.5em)
  // Pandoc wraps every table in align(center), which cells set to `auto`
  // would inherit. Put the context back to the left.
  show table: it => align(left, it)
  show figure: set block(breakable: true, above: 1.2em, below: 1.3em)

  // ─── Block quotations ────────────────────────────────────────────────────
  show quote.where(block: true): it => block(
    width: 100%,
    fill: rgb(pal.band),
    stroke: (left: 2pt + accent.lighten(55%)),
    inset: (left: 11pt, right: 10pt, top: 8pt, bottom: 8pt),
    radius: (right: 1.5pt),
    breakable: true,
    above: 1.15em,
    below: 1.15em,
    {
      set text(size: len(type.quote_size))
      set par(leading: 0.76em)
      it.body
    },
  )

  // ─── Lists ───────────────────────────────────────────────────────────────
  set list(
    indent: 0.6em,
    body-indent: 0.55em,
    spacing: 0.82em,
    marker: text(fill: accent.lighten(20%))[•],
  )
  set enum(indent: 0.6em, body-indent: 0.55em, spacing: 0.82em)

  // ─── Inline code ─────────────────────────────────────────────────────────
  // Used for the values a document leaves to be filled in — a protocol
  // number, an IBAN, a signature — which read better as a field than as text.
  show raw.where(block: false): it => box(
    fill: rgb(pal.band),
    inset: (x: 3.5pt, y: 0pt),
    outset: (y: 3.2pt),
    radius: 2pt,
    text(font: cfg.fonts.mono, size: em-of(type.code_size), fill: rgb(pal.muted), it.text),
  )

  show raw.where(block: true): it => block(
    width: 100%,
    fill: rgb(pal.band),
    inset: 9pt,
    radius: 2pt,
    breakable: true,
    above: 1.15em,
    below: 1.15em,
    text(font: cfg.fonts.mono, size: len(type.table_size), fill: rgb(pal.ink), it),
  )

  show link: set text(fill: accent.darken(20%))

  // Room for the header band on the first page. Typst has one top margin for
  // the whole document, so the first page buys its extra height here.
  v(len(cfg.page.first_page_extra))

  body

  // Room for the footer band on the last page, for the same reason.
  block(height: len(cfg.page.footer_reserve), width: 100%)
}
