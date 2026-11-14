# Kernel workload guide: review handoff

This is a working handoff, not part of the proposed upstream documentation.
Transfer it to the other computer separately, or include it temporarily in a
branch commit and remove it before preparing upstream patches.

## Current goal

Develop the kernel documentation and tooling patch series for identifying
features needed by a workload, reducing a kernel configuration, and measuring
the resulting build. Respond to Thorsten Leemhuis's review:

https://lore.kernel.org/linux-doc/6fac8906-e96c-4241-882a-736c37b77004@leemhuis.info/

The current branch is `mlw-minimize-docs`. At handoff, HEAD is `4156a55ea`
(`scripts: Rewrite kernel-sloc in pure Python`). The work described below is
unstaged and uncommitted. The user plans to review it and may make a single
commit to push before continuing on another computer.

## Changes for review

- Rename `Documentation/admin-guide/kernel-minimization.rst` to
  `Documentation/admin-guide/kernel-tailoring.rst` and update its title,
  admin-guide index, cross-references, and MAINTAINERS entry. Git currently
  shows a deletion and an untracked file until the rename is staged.
- Make source acquisition more self-contained; describe generic cross-build
  prerequisites as well as the existing Debian/Ubuntu example.
- Distinguish application requirements from platform, recovery, diagnostics,
  safety, and security requirements, including those absent from a trace.
- Explain that `kvm_guest.config` adds options to an existing configuration
  rather than replacing a baseline; this QEMU example does not require KVM.
- Add safety and security guidance: compare resolved configurations against a
  trusted target baseline, review the kernel's generic and arm64 hardening
  fragments and `Documentation/security/self-protection.rst`, and verify
  resolved dependencies and behavior on the target.
- Reference ELISA's
  [kconfig-safety-check](https://github.com/elisa-tech/kconfig-safety-check)
  with limitations: at revision `6136889f62fe`, its checks have an upper
  kernel-version limit of 6.7. This tree reports 6.19.0-rc2, so the checker
  can omit applicable checks; a passing or empty report is not proof of
  security.

## Naming remains open

The user is reconsidering "tailoring" and "minimizing": the guide is about
reducing configuration options or determining required features, and also
measuring the resulting small kernel. The existing separate guide is titled
"How to quickly build a trimmed Linux kernel". Candidate titles to discuss:

- "Building and measuring a kernel for a single workload" -- covers the full
  workflow without claiming a minimum.
- "Configuring and measuring a kernel for a single workload" -- emphasizes
  the configuration work as well as measurement.
- "Measuring a small kernel for a single workload" -- foregrounds measurement,
  though it says less about how the configuration is reduced.
- "Reducing and measuring a kernel for a single workload" -- explicitly names
  reduction, though the guide also starts from a small configuration.

No new name has been chosen. If changed, update the filename, title, index,
cross-references, MAINTAINERS entry, and any patch metadata together.

## Draft revision changelogs and feedback credit

The following is draft text for the next posted revision, subject to the
final diff and series organization. The linked review responds to the posted
v2, so the next publicly posted revision would normally be v3. Do not label
these edits as changes from v1 to v2 or replace the existing v2 history.

Proposed addition to the cover letter:

```text
Changes since v2:
  - Revise the workload guide's title and terminology, and include the
    core source acquisition commands alongside links to further details.
  - Separate workload requirements from platform and other system
    requirements. Clarify the choice of baseline and the role of the
    kvm_guest.config fragment.
  - Explain the security implications of starting from tinyconfig and
    point to kernel hardening guidance and configuration review.

Thanks to Thorsten Leemhuis for the review and suggestions on the guide:
https://lore.kernel.org/linux-doc/6fac8906-e96c-4241-882a-736c37b77004@leemhuis.info/
```

Proposed addition after the `---` separator in the workload-guide patch:

```text
Changes since v2:
 - Revise the guide's title and wording, and include the essential source
   acquisition commands (suggested by Thorsten Leemhuis).
 - Distinguish workload and platform requirements, and clarify the role of
   kvm_guest.config in choosing a baseline (Thorsten Leemhuis).
 - Discuss security configuration, including tinyconfig's limitations and
   kernel hardening references (prompted by Thorsten Leemhuis).
```

Adjust the title wording to match the final choice. The user separately
requested consideration of ELISA's checker; do not attribute that specific
suggestion to Thorsten. His feedback also suggested testing another
distribution; record any such change or test only if actually performed.
Credit these comments as suggestions or review feedback, not `Reviewed-by` or
`Acked-by`: the linked email does not provide either tag. Check the full
mailing-list discussion for additional feedback and tags before finalizing
the series. The kernel-sloc Python rewrite commit mentions reviewer feedback
but does not identify the reviewer; find the original email before assigning
credit or drafting an attributed script changelog.

Preserve the following existing v2 cover-letter history, which credits
Sashiko, in addition to the new revision notes:

```text
Changes in v2:
  - Reorder the series so the workload tracing update precedes the kernel
    minimization guide. The guide refers to the "Tracing a minimal user
    space" and "Mapping observations to configuration" sections added by
    the tracing update, so those sections now exist before they are
    referenced (reported by Sashiko).
  - Move the cross-references from the workload tracing guide to the
    kernel minimization guide into the minimization patch, so no patch
    refers to a document added later in the series.
  - Create the Workload analysis MAINTAINERS entry in the tracing patch and
    extend it with kernel-minimization.rst in the minimization patch.
  - No other content changes.
```

The last line describes v2 only, not the next revision. Preserve these
existing individual-patch notes after `---` as well:

```text
Workload tracing patch, changes in v2:
 - Now precedes the kernel minimization guide.
 - Creates the Workload analysis MAINTAINERS entry.
 - Refers to "scripts/kernel-sloc --help" instead of the minimization guide,
   which is added later in the series.

Workload guide patch, changes in v2:
 - Now follows the workload tracing update.
 - Adds the cross-references from the workload tracing guide to this guide.
 - Adds this file to the existing Workload analysis MAINTAINERS entry.
```

Historical names in these notes describe the previous revision; they do not
need to be silently rewritten when a new filename is chosen. Keep patch
changelogs below `---`, and update the cover letter's patch list, statistics,
rendered links, test results, and tool-use disclosure to reflect the final
series. These drafts are not substitutes for reviewing the full feedback.

## Validation and outstanding work

- The arm64 tinyconfig recipe was resolved using an existing `linux-dev`
  container with the cross-compiler. Required initramfs, ELF, serial, and
  console options resolved as expected. The resulting config disabled
  `RANDOMIZE_BASE`, `STACKPROTECTOR`, `FORTIFY_SOURCE`, `HARDENED_USERCOPY`,
  and `INIT_ON_ALLOC_DEFAULT_ON`; `STRICT_KERNEL_RWX` remained enabled.
- `git diff --check`, checkpatch on the new guide, and a focused check of RST
  heading lengths, `:doc:` targets, and trailing whitespace passed.
- `make htmldocs SPHINXDIRS=admin-guide` could not run: Sphinx is not
  installed locally or in the inspected existing containers. A real Sphinx
  build remains to be done.
- The revised recipe was not boot-tested in QEMU, and the instructions were
  not tested on Fedora. The reviewer asked for another distribution to be
  considered; avoid claiming such a test until it is actually performed.
- Review the naming and the hardening guidance, including whether the
  version-specific checker caveat belongs in the upstream text. Validate the
  final documentation and cross-references after any rename.

## Patch preservation

The in-progress formatted v2 series is in `~/patches/v2/` on the original
computer, with a cover letter and individual patch changelogs. Those files were
not regenerated or modified during this work. They are outside this Git
repository and will **not** travel with a push: copy them to the work computer
or otherwise preserve their contents before regenerating patches. Preserve and
update the existing cover-letter and per-patch changelogs rather than
overwriting them with freshly generated files.

The branch also includes later kernel-sloc test and Python rewrite commits
that are not represented in those original formatted v2 files. Decide how to
integrate those changes into the next series before regenerating it.

Do not stage, commit, amend, or send patches on the user's behalf without
further instruction. The user sends patch emails themselves.
