# Security

## Reporting a vulnerability

Please report privately rather than in a public issue: open a
[security advisory](https://github.com/melasistema/mela-letterhead/security/advisories/new)
on this repository, or write to **info@melasistema.com**.

Include what you did, what happened, and the versions `mela-letterhead check`
prints — this tool is mostly a layer over two other programs, and which ones
you have matters.

This is a one-person project. You should get an acknowledgement within a week.
Fixes go out as a patch release, and the advisory is published with it and
credits you unless you would rather it did not.

## What is in scope

The tool reads a configuration file and some Markdown, and writes a PDF. The
interesting question is what it does with a file it did not write, and the
answer is deliberately narrow, with one loud exception below:

- **Paths.** The logo and the page background are read relative to
  `letterhead.yaml`; pictures in a document are read relative to that document.
  A path escaping the project — through `..`, a symlink, an absolute path — and
  something outside it being read into the build directory or into the PDF is
  worth reporting.
- **A crafted `letterhead.yaml` or Markdown file causing anything other than a
  named error.** YAML is loaded with `yaml.safe_load`, which does not construct
  arbitrary Python objects. If a configuration file gets code to run, or writes
  outside the project, that is a vulnerability.
- **Anything reaching the network.** Nothing here does. A picture given as a
  URL is refused by name rather than fetched, and no configuration key names a
  remote resource. A build that makes a network request is a bug regardless of
  what it requested.
- **The build directory.** `.letterhead-build/<slug>/` is written under the
  project and holds only copies of things the document named. A slug or a
  filename that escapes it is in scope.

## What is not a vulnerability

**`markdown.extra_args` runs programs, by design.** It is appended to the
Pandoc command line, and Pandoc's `--lua-filter`, `--filter` and `-F` name
programs to execute. That makes `letterhead.yaml` executable configuration.

A `letterhead.yaml` that runs a command you did not intend is therefore working
as documented, and reports of that form will be closed with a pointer to this
paragraph. The boundary is where you decide to build with a file: **treat a
letterhead you did not write the way you would treat a script somebody sent
you.** Read it first. This is noted in the README beside the setting.

The same goes for Pandoc and Typst themselves. They are separate programs with
their own advisories; a defect in how Typst parses an SVG belongs upstream,
though we would still like to hear about it, because the fix here may be to
raise the minimum version the tool accepts.

## Versions

Fixes land on the latest release. There are no maintained older branches —
0.x means the current version is the supported one.
