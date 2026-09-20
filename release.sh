#!/usr/bin/env bash
#
# Cut a release.
#
#     ./release.sh              propose the version from the commits
#     ./release.sh 0.3.0        use this version instead
#     ./release.sh --dry-run    say what would happen and change nothing
#
# The version lives in three places and the changelog in two more — the
# section heading and the link definitions at the foot — and a tag pushed
# with any of them out of step fails in CI, after the tag is already public.
# This does all five edits from one number, and checks what the workflow will
# check before the tag exists rather than after.
#
# What it does not do is write the changelog. The commits propose a version,
# which is mechanical; the entry explaining what changed and why is prose, and
# this opens a draft in your editor rather than pretending otherwise. If you
# have already written the entry under `## [Unreleased]`, that is what gets
# promoted and the draft is skipped.
#
# Nothing is pushed. The last line tells you how.

set -euo pipefail

readonly REPO="https://github.com/melasistema/mela-letterhead"

# The subject grammar, spelled exactly as .githooks/commit-msg spells it — a
# commit the hook would refuse must not quietly decide a version number here.
readonly TYPES='build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test'
readonly SCOPE='(\([a-z0-9._/-]+\))?'

readonly CHANGELOG="CHANGELOG.md"
readonly PYPROJECT="pyproject.toml"
readonly INIT="src/mela_letterhead/__init__.py"

bold=$(tput bold 2>/dev/null || true)
dim=$(tput dim 2>/dev/null || true)
red=$(tput setaf 1 2>/dev/null || true)
green=$(tput setaf 2 2>/dev/null || true)
off=$(tput sgr0 2>/dev/null || true)

say()  { printf '%s\n' "$*"; }
step() { printf '\n%s%s%s\n' "$bold" "$*" "$off"; }
note() { printf '  %s%s%s\n' "$dim" "$*" "$off"; }
good() { printf '  %s✓%s  %s\n' "$green" "$off" "$*"; }
die()  { printf '\n%s✗%s  %s\n' "$red" "$off" "$*" >&2; exit 1; }

confirm() {
    [ "$assume_yes" = yes ] && return 0
    printf '\n%s [y/N] ' "$1"
    read -r reply
    [ "$reply" = y ] || [ "$reply" = Y ]
}

# sed -i spells itself differently on BSD and GNU; this spells it neither way.
rewrite() {
    local file=$1 expression=$2
    sed "$expression" "$file" > "$file.release-tmp"
    mv "$file.release-tmp" "$file"
}

# Rewrite the first `<prefix>"..."` line of a file. Not sed: the obvious
# `0,/^version/s//…` is a GNU address that BSD sed ignores without a word,
# which silently releases the old version number on a Mac.
set_version() {
    local file=$1 prefix=$2
    awk -v prefix="$prefix" -v version="$version" '
        !done && index($0, prefix) == 1 {
            printf "%s\"%s\"\n", prefix, version
            done = 1
            next
        }
        { print }
    ' "$file" > "$file.release-tmp"
    mv "$file.release-tmp" "$file"
}

# ---------------------------------------------------------------- arguments

wanted=""
dry_run=no
assume_yes=no
edit=yes

while [ $# -gt 0 ]; do
    case $1 in
        --dry-run)  dry_run=yes ;;
        --yes|-y)   assume_yes=yes ;;
        --no-edit)  edit=no ;;
        -h|--help)  sed -n '3,21p' "$0" | cut -c3-; exit 0 ;;
        -*)         die "unknown option $1" ;;
        *)          wanted=${1#v} ;;
    esac
    shift
done

cd "$(git rev-parse --show-toplevel)"

# ------------------------------------------------------------ is this sane?

step "Where we are"

branch=$(git rev-parse --abbrev-ref HEAD)
[ "$branch" = master ] || [ "$branch" = main ] \
    || die "on $branch — releases are cut from master"
good "on $branch"

[ -z "$(git status --porcelain)" ] \
    || die "the working tree is dirty; commit or stash first"
good "working tree clean"

git fetch --quiet --tags origin 2>/dev/null || note "could not reach origin"
if upstream=$(git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null); then
    behind=$(git rev-list --count "HEAD..$upstream")
    [ "$behind" -eq 0 ] || die "$behind commit(s) behind $upstream — pull first"
    good "up to date with $upstream"
fi

# ------------------------------------------------------- what has landed

current=$(grep -m1 '^version = ' "$PYPROJECT" | cut -d'"' -f2)
last_tag=$(git describe --tags --abbrev=0 2>/dev/null || true)
range=${last_tag:+$last_tag..}HEAD

subjects=$(git log --format=%s "$range" || true)
[ -n "$subjects" ] || die "no commits since ${last_tag:-the beginning} to release"

step "Commits since ${last_tag:-the beginning}"
printf '%s\n' "$subjects" | sed 's/^/  /'

# A subject that the commit-msg hook would have refused cannot be classified,
# and a release that silently ignores commits is worse than one that stops.
strays=$(printf '%s\n' "$subjects" | grep -Ev "^($TYPES)$SCOPE!?: .+" || true)
if [ -n "$strays" ]; then
    say ""
    note "these are not conventional commits and count for nothing:"
    printf '%s\n' "$strays" | sed "s/^/  $dim  ✗ /;s/\$/$off/"
    note "install the hook so this cannot recur: git config core.hooksPath .githooks"
fi

# ------------------------------------------------------------- the version

IFS=. read -r major minor patch <<< "$current"

if printf '%s\n' "$subjects" | grep -qE "^($TYPES)$SCOPE!: " \
   || git log --format='%B' "$range" | grep -q '^BREAKING CHANGE'; then
    level=breaking
elif printf '%s\n' "$subjects" | grep -qE "^feat$SCOPE!?: "; then
    level=feature
elif printf '%s\n' "$subjects" | grep -qE "^fix$SCOPE!?: "; then
    level=fix
else
    level=none
fi

case $level in
    # Before 1.0 the major number is not a promise yet, so a breaking change
    # moves the minor. This is what release-please did and what the ecosystem
    # reads; pass the number yourself to say otherwise.
    breaking) if [ "$major" -eq 0 ]
              then proposed="$major.$((minor + 1)).0"; why="a breaking change, and 0.x keeps it in the minor"
              else proposed="$((major + 1)).0.0"; why="a breaking change"
              fi ;;
    feature)  proposed="$major.$((minor + 1)).0"; why="a feat: commit" ;;
    fix)      proposed="$major.$minor.$((patch + 1))"; why="fix: commits only" ;;
    none)     proposed="$major.$minor.$((patch + 1))"; why="nothing that changes the package — you may not want to release at all" ;;
esac

if [ -n "$wanted" ]; then
    version=$wanted
    why="you asked for it; the commits proposed $proposed"
else
    version=$proposed
fi

printf '%s\n' "$version" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+([-+].+)?$' \
    || die "$version is not a version number"
git rev-parse -q --verify "refs/tags/v$version" >/dev/null \
    && die "v$version already exists"

step "Version"
say "  $current  →  ${bold}$version${off}"
note "$why"

if [ "$dry_run" = yes ]; then
    step "Dry run — nothing was changed."
    exit 0
fi

confirm "Bump to $version?" || die "stopped"

# --------------------------------------------------------- the notes

work=$(mktemp -d)
trap 'rm -rf "$work" "$CHANGELOG.release-tmp" "$PYPROJECT.release-tmp" "$INIT.release-tmp"' EXIT
body=$work/body.md

# Everything already written under `## [Unreleased]`. If you kept the changelog
# as you went, this is the entry and there is nothing to draft.
awk '
    index($0, "## [Unreleased]") == 1 { found = 1; next }
    found && index($0, "## [") == 1   { exit }
    found && /^\[[^]]+\]: /           { exit }
    found                             { print }
' "$CHANGELOG" | sed -e '/./,$!d' > "$body"

if grep -q '[^[:space:]]' "$body"; then
    good "promoting the entry already written under [Unreleased]"
else
    note "no [Unreleased] entry — drafting one from the commits to rewrite"
    {
        collect() {  # heading, subject pattern
            local matched
            matched=$(printf '%s\n' "$subjects" | grep -E "$2" \
                      | sed -E 's/^[a-z]+(\(([^)]+)\))?!?: /- (\2) /;s/- \(\) /- /' || true)
            [ -n "$matched" ] || return 0
            printf '### %s\n\n%s\n\n' "$1" "$matched"
        }
        collect Added   "^feat$SCOPE!?: "
        collect Changed "^(refactor|perf|style|revert)$SCOPE!?: "
        collect Fixed   "^fix$SCOPE!?: "
    } > "$body"
fi

if [ "$edit" = yes ]; then
    cat >> "$body" <<'DRAFT'

<!-- Everything above becomes the notes of the GitHub release, verbatim.
     Say what changed and why it matters to somebody using the tool, not what
     the commit did. Delete this comment and every line you do not want. -->
DRAFT
    say ""
    note "opening ${VISUAL:-${EDITOR:-vi}} — write the entry, save, quit"
    "${VISUAL:-${EDITOR:-vi}}" "$body"
    rewrite "$body" '/^<!--/,/-->$/d'
fi

grep -q '[^[:space:]]' "$body" || die "the entry is empty; nothing to release"

# ------------------------------------------------------------- the edits

step "Editing"

set_version "$PYPROJECT" 'version = '
good "$PYPROJECT"

set_version "$INIT" '__version__ = '
good "$INIT"

previous=${last_tag:-v0.0.0}
awk -v version="$version" -v date="$(date +%F)" -v body="$body" \
    -v repo="$REPO" -v previous="$previous" '
    # The new section goes under an emptied [Unreleased]; whatever was there
    # has been lifted into the body file already.
    index($0, "## [Unreleased]") == 1 {
        print
        print ""
        printf "## [%s] — %s\n\n", version, date
        while ((getline line < body) > 0) held[++n] = line
        while (n > 0 && held[n] ~ /^[[:space:]]*$/) n--   # trailing blanks
        for (i = 1; i <= n; i++) print held[i]
        print ""
        skipping = 1
        next
    }
    skipping && index($0, "## [") == 1 { skipping = 0 }
    skipping && /^\[[^]]+\]: /         { skipping = 0 }
    skipping                           { next }

    # And the link definitions at the foot, which are the half of this that is
    # always forgotten.
    index($0, "[Unreleased]: ") == 1 {
        printf "[Unreleased]: %s/compare/v%s...HEAD\n", repo, version
        printf "[%s]: %s/compare/%s...v%s\n", version, repo, previous, version
        next
    }
    { print }
' "$CHANGELOG" > "$CHANGELOG.release-tmp"
mv "$CHANGELOG.release-tmp" "$CHANGELOG"
good "$CHANGELOG"

# ------------------------------------------------- what the workflow checks

step "What the release workflow will check"

for file in "$PYPROJECT" "$INIT"; do
    grep -q "\"$version\"" "$file" || die "$file did not take the version"
done
good "the tag and the package agree"

# The workflow's own awk, so this is the text and not an approximation of it.
awk -v want="## [$version]" '
    index($0, want) == 1            { found = 1; next }
    found && index($0, "## [") == 1 { exit }
    found && /^\[[^]]+\]: /         { exit }
    found && NF == 0                { if (started) held = held "\n"; next }
    found { printf "%s%s\n", held, $0; held = ""; started = 1 }
' "$CHANGELOG" > "$work/notes.md"

grep -q '[^[:space:]]' "$work/notes.md" \
    || die "CHANGELOG.md has no '## [$version]' section the workflow can read"
good "the changelog has notes to publish"

if command -v pytest >/dev/null 2>&1; then
    printf '  '
    pytest -q || die "the tests fail — the release workflow runs them too"
    good "the tests pass"
else
    note "pytest is not on PATH; the workflow will run the suite instead"
fi

# CI fails a release branch for either of these, and finding out from a red
# tick after the tag is public is the whole thing this script exists to avoid.
if command -v ruff >/dev/null 2>&1; then
    ruff check --quiet src tests tools || die "ruff has something to say"
    good "ruff is happy"
else
    note "ruff is not on PATH; CI will run it instead"
fi

# The schema is generated from DEFAULT_CONFIG and committed inside the package,
# which is how `pipx install` carries it and how `init` hands a project its own
# copy. A release that ships a setting the schema has never heard of underlines
# that setting, in red, in the editor of everybody who takes the upgrade.
python3 tools/generate_schema.py --check >/dev/null \
    || die "the schema is stale — run: python3 tools/generate_schema.py"
good "the schema is up to date"

if command -v mypy >/dev/null 2>&1; then
    mypy --no-error-summary || die "mypy has something to say"
    good "mypy is happy"
else
    note "mypy is not on PATH; CI will run it instead"
fi

step "The release notes, as GitHub will show them"
say ""
sed 's/^/  /' "$work/notes.md"

confirm "Commit chore(release): $version and tag v$version?" || {
    say ""
    note "nothing committed; the edits are in your working tree"
    note "undo them with: git checkout -- $PYPROJECT $INIT $CHANGELOG"
    exit 0
}

# ----------------------------------------------------------- commit and tag

git add "$PYPROJECT" "$INIT" "$CHANGELOG"
git commit --quiet -m "chore(release): $version"
git tag -a "v$version" -m "v$version"

step "Done"
good "$(git log -1 --format='%h %s')"
good "tag v$version"
say ""
say "  Push it:"
say "      ${bold}git push && git push origin v$version${off}"
say ""
note "nothing has left this machine yet; the tag is what triggers the release"
note "which cuts the GitHub release and then publishes to PyPI — and PyPI"
note "will not take the same version twice, so the tag is the point of no return"
