.. SPDX-License-Identifier: (GPL-2.0+ OR CC-BY-4.0)

=================================================
Minimizing a Linux kernel for a single workload
=================================================

:Authors: - ELISA Aerospace Working Group

This document explains how to trim a Linux kernel for a single, known workload,
check that it still runs, and measure the resulting build. The examples are
starting points to adapt to your hardware and workload, not configurations to
copy unchanged.

A smaller kernel carries less code to build, boot, review, and maintain. How
much that matters depends on the situation: a developer trimming a test kernel
cares about build time, while an integrator preparing a kernel for analysis or
for a safety- or security-critical deployment cares about how much code must be
understood and justified. This guide stays with the mechanics of trimming and
measuring; where a particular step is useful for one of those analyses, it is
called out as an example, not as a requirement.

This guide builds on, rather than repeats, several existing documents:

* :doc:`quickly-build-trimmed-linux` for the mechanics of getting, building,
  and installing a kernel. This guide assumes you have followed it at least
  once and reuses its sections by name below -- in particular its "Download the
  sources" and "Define the build configuration for your kernel" steps. Note
  that guide targets a kernel built **natively for the machine you are on**; the
  cross-compiled, boot-in-QEMU angle used here is the main thing this guide adds
  on top of it (see `Building: native vs cross-compiled`_).
* :doc:`workload-tracing` for discovering the subsystems a workload uses, and
  :doc:`/trace/ftrace` for tracing the kernel functions it reaches.
* :doc:`/dev-tools/kcov` and :doc:`/dev-tools/gcov` for coverage collection.
* :doc:`/kbuild/kconfig` and :doc:`/kbuild/kconfig-language` for the
  configuration mechanics, and :doc:`/kbuild/kbuild` for build variables such
  as ``ARCH`` and ``CROSS_COMPILE``.

Baseline scenario
=================

The walkthrough assumes the simplest possible launch model, which keeps the
chain from "what the workload needs" to "what the kernel must provide" short:

   **The kernel launches the workload directly as PID 1. There is no init
   system, no service manager, and no general multi-user user space.**

For the initramfs example below, the kernel runs ``/init`` by default; use
``rdinit=<path>`` to select a different program in that archive. ``init=<path>``
selects init after mounting a real root filesystem; it does not override a
working initramfs ``/init``.

With this baseline, the user space is essentially the application plus the C
library it links against. The decision cascades into the configuration: no
service management, no getty/login, only the library and kernel features the
application itself exercises.

The worked example boots an ``arm64`` kernel under QEMU with a static "hello
world" program as PID 1. See `A minimal PID 1 workload`_ below.

This walkthrough assumes a monolithic build: ``CONFIG_MODULES=n`` and all
required kernel features and drivers built in (``=y``). It does not build,
load, measure, or account for loadable modules. Disabling module support does
not convert existing ``=m`` selections into built-ins; explicitly enable any
needed features as ``=y`` and check the resolved configuration.

Building and trimming
=====================

Change one feature group at a time, rebuild, and check that the workload still
runs. The measurement examples below can help compare working configurations.

Prerequisites
-------------

Follow "Install build requirements" in :doc:`quickly-build-trimmed-linux`
for the native build tools. On a Debian/Ubuntu x86_64 host, this example adds::

    sudo apt install gcc-aarch64-linux-gnu qemu-system-arm file

The cross-compiler package brings in matching binutils and, with the normal
recommended packages, the target libc headers and static library. ``qemu-system-arm`` provides
``qemu-system-aarch64``; ``file`` checks the application binary. Other tools
are introduced where they are used.

Get the sources
---------------

Retrieve the kernel sources exactly as described in
:doc:`quickly-build-trimmed-linux` ("Download the sources"). For a workload
that must track a long-lived kernel, follow that guide's instructions for
adding a stable/longterm branch rather than building bleeding-edge mainline, so
you measure against a kernel with a long maintenance window. All commands below
run from the resulting source tree.

Building: native vs cross-compiled
----------------------------------

The trimmed-build guide builds a kernel **natively, for the machine you are
running on**, and installs it there. This guide instead builds for a target
architecture and boots the result under QEMU, so nothing is installed on your
host. The mechanics of cross-building are not specific to minimization and are
documented in :doc:`/kbuild/kbuild` (the ``ARCH`` and ``CROSS_COMPILE``
variables); set them once for the worked example::

    export ARCH=arm64
    export CROSS_COMPILE=aarch64-linux-gnu-

Every ``make`` below (``defconfig``, ``tinyconfig``, ``olddefconfig``,
``Image``) then honours them. For a native arm64 build, omit ``CROSS_COMPILE`` and use the native tools.
An x86 kernel or application cannot substitute for the arm64 images in the
QEMU commands. Other architectures need their own image target, console,
platform support, and emulator. The trimmed-build guide's "Install your kernel"
and Secure Boot steps do not apply to this QEMU experiment.

Build in the source tree, as in the trimmed-build guide. Save a working
``.config`` before changing it so you can restore it if necessary. Keep the
matching ``vmlinux`` when resolving debug information or coverage PCs.
``make clean`` preserves ``.config`` but removes build artifacts; do not use
``mrproper`` between changes.

Iterate toward minimal
----------------------

Pick a direction. These mirror the two bases the trimmed-build guide's "Define
the build configuration for your kernel" section describes -- starting from an
existing (large) config versus starting from scratch:

* **Top-down** -- start from a working configuration and remove features,
  re-testing after each removal. For this arm64 QEMU example, build
  ``defconfig`` as the baseline::

      make defconfig
      ./scripts/config -d MODULES
      make olddefconfig
      make clean
      make -j"$(nproc)" Image

  Follow `A minimal PID 1 workload`_ to compile, pack, and boot the application.
  Require ``hello world`` and no panic before treating this as a known-good
  baseline (pass ``-m 512M`` or ``-m 1G`` to QEMU for defconfig images to avoid
  exhausting the default 128 MB machine memory during driver initialization).
  For a native target, the trimmed-build guide's
  ``localmodconfig``/``olddefconfig`` approach is another starting point; do not
  use the host's configuration for an unrelated cross-compiled target.
  Save the working configuration, then change one group::

      cp .config config.before
      ./scripts/config -d IPV6
      make olddefconfig
      make clean
      make -j"$(nproc)" Image

* **Bottom-up** -- start from almost nothing and add only what the workload
  needs::

      make tinyconfig
      ./scripts/config \
          -e PRINTK -e TTY -e SERIAL_AMBA_PL011 -e SERIAL_AMBA_PL011_CONSOLE \
          -e BINFMT_ELF -e BLK_DEV_INITRD -d MODULES
      make olddefconfig
      make clean
      make -j"$(nproc)" Image

  Beyond the serial options, this example needs ``PRINTK``, ``BLK_DEV_INITRD``,
  and ``BINFMT_ELF`` for visible output, the external initramfs, and ELF
  execution. Arm64 selects its device-tree, interrupt-controller, timer, and
  AMBA support; those are not supplied by the
  serial driver. This is a small bootable starting point for QEMU ``virt``,
  not a universally minimal or production-ready configuration. Inspect the
  resolved config: ``scripts/config`` edits requests, and unmet dependencies
  can cause ``olddefconfig`` to discard them. Pack and boot the same PID 1
  application as above; building ``defconfig`` first is not necessary for this
  direction.

To browse the configuration tree interactively with help text in view, use
``make menuconfig`` (needs ``libncurses-dev``), as described in the
trimmed-build guide's "Individual adjustments" section.

After each change, repeat the boot command in `A minimal PID 1 workload`_ with
the rebuilt image and the same application archive. For this example, require
``hello world`` and no panic. A QEMU timeout alone is not success: a failed
boot can also hang. To inspect changes against the saved configuration::

    scripts/diffconfig config.before .config > config.delta

Do not assume that ``tinyconfig`` to ``defconfig`` measures one subsystem:
optimization policy, platform drivers, and many unrelated settings change too.
For a single-group comparison, save the last resolved config as
``config.before``, change just that group, and clean/rebuild.

Deciding what to remove
=======================

Follow :doc:`workload-tracing` for syscall and kernel-path collection,
including "Tracing a minimal user space" for this PID 1 launch model and
"Mapping observations to configuration" for source/Kconfig analysis.
Re-test each removal with the same PID 1 workload.

Measuring
=========

The following measurements can help compare builds:

* **Source lines of code (SLOC)** -- a proxy for the amount of code to review.
  Two complementary counts are available (see `Counting kernel SLOC`_): a DWARF-based
  estimate of source lines represented in the linked image, and a ``cloc``
  count of whole compiled source files. Neither measures runtime coverage.
* **Image size** -- a sanity bound only, not a score; it depends on
  compression, compiler version, and optimization level.
* **Boots? / workload passes?** -- the configuration is only valid if the
  target still runs.

For meaningful comparisons, use consistent workload inputs, tool versions,
build options, and instrumentation. These QEMU checks do not validate target
hardware, timing, failure recovery, or a larger workload.

Counting kernel SLOC
--------------------

Install ``cloc`` for compiled-source counts and ensure ``python3`` is available
for generating the compilation database. On Debian/Ubuntu::

    sudo apt install cloc python3

Use ``scripts/kernel-sloc``; ``scripts/kernel-sloc --help`` lists its modes,
requirements, and tool overrides. Successful runs print one integer on stdout
and a human-readable summary on stderr. Errors exit non-zero without a count.
It offers two kernel counts:

* ``dwarf`` -- resolves DWARF line-table addresses in a ``vmlinux`` built with
  ``CONFIG_DEBUG_INFO`` to distinct full-path ``file:line`` pairs using GNU
  ``objdump`` and ``addr2line``. Optimization, inlining, and the quality of the
  debug information affect this estimate; it is not an exact mapping of every
  instruction to all contributing source lines.
* ``kernel`` -- wraps ``cloc`` over the unique sources listed in
  ``compile_commands.json``. It counts code lines in whole files, including
  inactive preprocessor branches, but does not follow included headers. It is
  therefore not a strict upper bound on the DWARF count.

The DWARF SLOC metric needs a ``vmlinux`` built with debug information.
Enable it before rebuilding and counting; this does not instrument execution.
Follow the trimmed-build guide's "Debug symbols" section to enable it. Only the
DWARF line table is needed here, so the symbol-table options that section also
turns on (``KALLSYMS``, ``KALLSYMS_ALL``) are left out::

    ./scripts/config -d DEBUG_INFO_NONE \
        -e DEBUG_KERNEL -e DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT \
        -d DEBUG_INFO_BTF -d DEBUG_INFO_SPLIT
    make olddefconfig
    make clean
    make -j"$(nproc)" Image

Selecting the DWARF choice enables ``CONFIG_DEBUG_INFO`` through Kconfig; do not
rely on setting that hidden symbol directly. BTF is unnecessary for this
metric. Split DWARF needs separate files and is not used in this walkthrough.
Check that ``CONFIG_DEBUG_INFO=y`` survives ``olddefconfig``. Reapply these
settings after starting from ``tinyconfig``, which resets debug options, and
rebuild before measuring. Keep this debug policy consistent across compared builds.

With module support disabled, ``dwarf vmlinux`` measures the linked kernel ELF.
``kernel`` counts sources listed in its compilation database, including generated
sources, assembly, and host helpers when present. The database is an inventory
of compilations, not proof that every file is linked into the target image.
Use ``make clean`` before each changed build and regenerate the database after
building; stale ``.cmd`` files or a database can retain previous sources.
Neither count here includes loadable modules.

If the database is missing, ``kernel`` runs the generator automatically. For
an out-of-tree build, use the generator's ``-d`` option and pass the build
directory to the counter.

.. code-block:: sh

    # debug-info estimate: distinct source lines represented in vmlinux
    scripts/kernel-sloc --report linked.json dwarf vmlinux > sloc-dwarf.txt

    # regenerate the database only after completing this clean build
    python3 scripts/clang-tools/gen_compile_commands.py
    scripts/kernel-sloc --report compiled.json kernel . > sloc-compiled.txt

For a cross build, select matching tools with
``CROSS_COMPILE=aarch64-linux-gnu- scripts/kernel-sloc dwarf vmlinux``.
``OBJDUMP`` and ``ADDR2LINE`` override the individual tool names; if only
``OBJDUMP`` is set to a conventional name ending in ``objdump``, the script
uses the same prefix for ``addr2line``.

The optional ``--report`` writes a JSON inventory without changing the integer
count on stdout. ``kernel`` lists unique compiled files; ``dwarf`` lists the
counted ``file:line`` pairs and function/file pairs resolved at those addresses.
This is not a complete function-symbol listing; debug information, optimization,
and inlining limit the mapping. Retain the reports to connect the built-code
inventory to observations from :doc:`workload-tracing`.

Separating code that is present from code that runs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

SLOC and its inventories describe built code, not execution. Use
:doc:`/dev-tools/gcov` for execution counts and :doc:`/dev-tools/kcov` for
task-scoped kernel PCs; `Dumping kernel coverage (kcov)`_ below adapts its
collector to PID 1. Save the target configuration before enabling
instrumentation, then restore and clean/rebuild for uninstrumented testing.
Boot, other tasks, interrupts, and recovery paths may be outside the collection
scope. Unobserved code remains a removal candidate to investigate and re-test,
not proof of an unnecessary feature.

Measuring the image
-------------------

Track image size to stay under a ceiling, not as a score::

    make Image.gz
    stat -c%s arch/arm64/boot/Image      # raw
    stat -c%s arch/arm64/boot/Image.gz   # compressed

Example progression
--------------------

Starting from the bootable ``tinyconfig`` recipe and adding one subsystem group
at a time
toward ``defconfig`` (the groups are what ``scripts/diffconfig`` shows between
the two), each step still booting the PID 1 workload, illustrates what each
group costs in code. Recording the SLOC delta per group is the useful output:
it shows which subsystems dominate the code base for a given workload, and a
large single-group jump is a prompt to check whether that group is really
required. The figures depend entirely on kernel version, architecture, and
toolchain, so generate your own with the steps above rather than reusing
published numbers.

Reducing the user space too
============================

For this small static program, the linked C library can dominate the user-space
binary size. A different libc (for example musl) can change both size and
syscall behavior; fewer library entry points do not automatically mean fewer
required kernel features. Rebuild, trace, and re-test the same workload before
accepting a library change.

``scripts/kernel-sloc --help`` describes the optional application/file and
source-tree counts. Compare deployed binaries and libraries too; a source-tree
count is not a deployed footprint.

A minimal PID 1 workload
========================

This is the "hello world" program booted as PID 1 in the walkthrough. There is
no init system, no shell, and no service manager -- the kernel execs it directly
as ``/init`` from an initramfs.

.. code-block:: c

    #include <stdio.h>
    #include <unistd.h>

    int main(void)
    {
        printf("hello world\n");
        fflush(stdout);

        /* PID 1 must never return. Idle forever. */
        for (;;)
            pause();

        return 0; /* not reached */
    }

Save it as ``ainit.c`` and build it statically so the kernel can exec it
with no dynamic loader or libraries present in the rootfs::

    aarch64-linux-gnu-gcc -static -O2 -o ainit ainit.c
    file ainit     # -> ELF 64-bit ... ARM aarch64 ... statically linked ...
    aarch64-linux-gnu-readelf -l ainit   # no INTERP segment
    aarch64-linux-gnu-readelf -d ainit   # no NEEDED entries

Pack the application as ``/init`` in a gzip-compressed ``newc`` archive.
Install ``cpio`` if needed; ``gzip`` is normally present on the build host::

    sudo apt install cpio
    mkdir -p rootfs
    cp ainit rootfs/init
    chmod 0755 rootfs/init
    ( cd rootfs && find . | cpio -o -H newc ) | gzip > initramfs.cpio.gz

With ``CONFIG_INITRAMFS_SOURCE=""``, the default built-in initramfs supplies
``/dev/console``, so this external archive only needs ``/init``.

Check the resolved configuration for built-in ``PRINTK``, ``TTY``,
``SERIAL_AMBA_PL011``, ``SERIAL_AMBA_PL011_CONSOLE``, ``BLK_DEV_INITRD``,
``RD_GZIP``, and ``BINFMT_ELF`` as in the bottom-up recipe. Boot the
rebuilt image with the same application archive::

    qemu-system-aarch64 -machine virt -cpu cortex-a57 -nographic \
        -kernel arch/arm64/boot/Image \
        -initrd initramfs.cpio.gz \
        -append 'console=ttyAMA0'

When booting larger or monolithic ``defconfig`` images, pass ``-m 512M`` or
``-m 1G`` to provide sufficient memory for driver initialization (the default
128 MB on QEMU ``virt`` can trigger out-of-memory panics on full configurations).

There is no ``root=`` and no disk image -- the initramfs is the root and the
kernel runs ``/init`` from it by default. The program prints ``hello world`` and
then parks in ``pause()`` forever, so it never triggers the ``Attempted to kill
init!`` panic. Close QEMU with ``Ctrl-a x``.

Probing a kernel feature
------------------------

To test a configuration decision, use a complete variant of ``ainit.c`` that
opens an IPv4 UDP socket. Save this as ``ainit-net.c``:

.. code-block:: c

    #include <errno.h>
    #include <stdio.h>
    #include <string.h>
    #include <sys/socket.h>
    #include <netinet/in.h>
    #include <unistd.h>

    int main(void)
    {
        int fd = socket(AF_INET, SOCK_DGRAM, 0);
        int error = fd < 0 ? errno : 0;

        printf("hello world\n");
        if (fd >= 0) {
            printf("NET-PROBE: IPv4/UDP socket available\n");
            close(fd);
        } else {
            printf("NET-PROBE: failed: errno=%d (%s)\n", error,
                   strerror(error));
        }
        fflush(stdout);
        for (;;)
            pause();
        return 0;
    }

Build the variant, replace the staged ``/init``, and repack::

    aarch64-linux-gnu-gcc -static -O2 -o ainit-net ainit-net.c
    cp ainit-net rootfs/init
    chmod 0755 rootfs/init
    ( cd rootfs && find . | cpio -o -H newc ) | gzip > initramfs-net.cpio.gz

Use the QEMU command above with ``-initrd initramfs-net.cpio.gz`` for
each selected kernel. Keep the hello-world archive unchanged. Expected results:

* The baseline with built-in ``NET=y`` and ``INET=y`` can create the socket.
* The bootable tiny recipe with ``NET`` disabled fails (normally ``ENOSYS``).
* ``NET=y`` without ``INET`` cannot provide this address family (normally
  ``EAFNOSUPPORT``); it may still provide other networking features.

Starting from the bootable tiny configuration, save its config before adding
IPv4 and rebuilding::

    cp .config config.before
    ./scripts/config -e NET -e INET
    make olddefconfig
    make clean
    make -j"$(nproc)" Image

Check the actual errno against the resolved configuration. Creating a
socket does not test packet I/O, routing, network interfaces, or application
protocols. This program reports an observation; a test harness must compare it
to the expected result. Any failure is not by itself proof that all networking
is absent.

Dumping kernel coverage (kcov)
------------------------------

Use the "Coverage collection" example in :doc:`/dev-tools/kcov` for collection,
buffer checks, and syscall results. The adaptations here are only for the
single-binary PID 1 launch: mount debugfs in the application, print to the
serial console, and idle instead of exiting, including on failure. Collection
still covers only the example's target syscall, not the boot or hello-world
application.

Save the target configuration, enable KCOV and debugfs along with the
debug-info settings from `Counting kernel SLOC`_ for symbolizing PCs, and
rebuild::

    cp .config config.before
    ./scripts/config -e KCOV -e DEBUG_FS \
        -d DEBUG_INFO_NONE \
        -e DEBUG_KERNEL -e DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT \
        -d DEBUG_INFO_BTF -d DEBUG_INFO_SPLIT
    make olddefconfig
    make clean
    make -j"$(nproc)" Image

Save the adapted PID 1 coverage collector as ``ainit-kcov.c``:

.. code-block:: c

    #include <errno.h>
    #include <stdio.h>
    #include <stddef.h>
    #include <stdint.h>
    #include <stdlib.h>
    #include <sys/types.h>
    #include <sys/stat.h>
    #include <sys/ioctl.h>
    #include <sys/mman.h>
    #include <sys/syscall.h>
    #include <sys/mount.h>
    #include <unistd.h>
    #include <fcntl.h>
    #include <linux/types.h>

    #define KCOV_INIT_TRACE		_IOR('c', 1, unsigned long)
    #define KCOV_ENABLE		_IO('c', 100)
    #define KCOV_DISABLE		_IO('c', 101)
    #define COVER_SIZE		(64 << 10)

    #define KCOV_TRACE_PC		0

    static _Noreturn void idle(int status)
    {
        puts(status ? "KCOV: FAILED" : "KCOV: complete");
        fflush(stdout);
        for (;;)
            pause();
    }

    int main(void)
    {
        int fd, error;
        long result;
        unsigned long *cover, n, i;

        if (mount("none", "/sys/kernel/debug", "debugfs", 0, NULL))
            perror("mount debugfs"), idle(1);

        fd = open("/sys/kernel/debug/kcov", O_RDWR);
        if (fd == -1)
            perror("open"), idle(1);

        if (ioctl(fd, KCOV_INIT_TRACE, COVER_SIZE))
            perror("ioctl"), idle(1);

        cover = (unsigned long *)mmap(NULL, COVER_SIZE * sizeof(unsigned long),
                                     PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        if ((void *)cover == MAP_FAILED)
            perror("mmap"), idle(1);

        if (ioctl(fd, KCOV_ENABLE, KCOV_TRACE_PC))
            perror("ioctl"), idle(1);

        __atomic_store_n(&cover[0], 0, __ATOMIC_RELAXED);
        errno = 0;
        result = syscall(SYS_read, -1, NULL, 0);
        error = errno;
        n = __atomic_load_n(&cover[0], __ATOMIC_RELAXED);

        if (ioctl(fd, KCOV_DISABLE, 0))
            perror("ioctl"), idle(1);

        if (result != -1 || error != EBADF) {
            fprintf(stderr, "unexpected read result: %ld, errno: %d\n",
                    result, error);
            idle(1);
        }
        if (!n || n >= COVER_SIZE - 1) {
            fprintf(stderr, "empty or full coverage buffer: %lu PCs\n", n);
            idle(1);
        }
        for (i = 0; i < n; i++)
            printf("0x%lx\n", cover[i + 1]);

        if (munmap(cover, COVER_SIZE * sizeof(unsigned long)))
            perror("munmap"), idle(1);
        if (close(fd))
            perror("close"), idle(1);

        idle(0);
    }

Compile statically and pack a separate archive, leaving hello-world unchanged::

    aarch64-linux-gnu-gcc -static -O2 -o ainit-kcov ainit-kcov.c
    mkdir -p rootfs-kcov/sys/kernel/debug
    cp ainit-kcov rootfs-kcov/init
    chmod 0755 rootfs-kcov/init
    ( cd rootfs-kcov && find . | cpio -o -H newc ) | gzip > initramfs-kcov.cpio.gz

Capture the serial log from the instrumented kernel (exit with ``Ctrl-a x``)::

    qemu-system-aarch64 -machine virt -cpu cortex-a57 -nographic \
        -kernel arch/arm64/boot/Image -initrd initramfs-kcov.cpio.gz \
        -append 'console=ttyAMA0 nokaslr' 2>&1 | tee kcov.log

Pass ``-m 512M`` or ``-m 1G`` if capturing coverage against a ``defconfig`` build.

Check for ``KCOV: complete`` with no failure marker or panic. Extract just the
PC lines from the boot log (stripping carriage returns from the serial console)::

    awk '{gsub(/\r/,""); if (NF == 1 && $1 ~ /^0x[0-9a-fA-F]+$/) print $1}' kcov.log > kcov-pcs.txt
    test -s kcov-pcs.txt

Follow :ref:`kcov-symbolizing-pcs` with the matching build's ``vmlinux`` and
arm64 tools to symbolize the extracted addresses::

    aarch64-linux-gnu-addr2line -f -i -e vmlinux < kcov-pcs.txt > kcov-symbols.txt

Extract unique ``file:line`` locations and strip discriminator suffixes::

    sed -nE 's/ \(discriminator [0-9]+\)//; /:[1-9][0-9]*$/p' kcov-symbols.txt | sort -u > kcov-lines.txt
    wc -l kcov-lines.txt

Comparing the count of unique executed kernel source lines against the total
linked DWARF SLOC gives the runtime reachability (kernel call coverage)
percentage for that syscall invocation::

    Kernel Call Coverage (%) = (Unique KCOV Executed Lines / Total DWARF Linked SLOC) * 100%

Compare resolved file/function paths with the SLOC inventories
for that build. Unobserved entries are candidates to investigate, not proof
that code is safe to remove. Module coverage is outside this walkthrough.

Comparing whole-kernel coverage (GCOV vs KCOV)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

KCOV is intentionally task-scoped for single-thread syscall tracing and
coverage-guided fuzzing, capturing only the code executed during calls on the
thread that enabled tracing. If the verification goal is structural code
coverage across the entire kernel -- including boot initialization, interrupt
handlers, background kernel daemons, and multi-process workloads -- use
:doc:`/dev-tools/gcov`. GCOV provides GCC/Clang compiler-level basic-block
counters across the entire kernel image and exports runtime coverage files
through ``/sys/kernel/debug/gcov``.

References
==========

* :doc:`quickly-build-trimmed-linux` -- building and installing a kernel.
* :doc:`workload-tracing` -- discovering subsystems used by a workload.
* :doc:`/trace/ftrace` -- in-kernel function tracing, for seeing which kernel
  functions a workload reaches.
* :doc:`/dev-tools/testing-overview` -- overview of kernel testing frameworks and coverage tools.
* :doc:`/dev-tools/kcov`, :doc:`/dev-tools/gcov` -- coverage collection.
* :doc:`/dev-tools/kselftest`, :doc:`/dev-tools/kunit/index` -- in-kernel unit testing and functional test suites.
* :doc:`/kbuild/kconfig`, :doc:`/kbuild/kconfig-language` -- configuration;
  :doc:`/kbuild/kbuild` -- ARCH / CROSS_COMPILE and other build variables.
* ``scripts/kernel-sloc`` -- the SLOC counter used for the metrics above.
* ``scripts/diffconfig``, ``scripts/bloat-o-meter`` -- related size/diff
  helpers.
* `Kernel Size Reduction Work <https://elinux.org/Kernel_Size_Reduction_Work>`_
  -- the earlier tinification effort that introduced ``make tinyconfig``, for
  background on which options dominate a small kernel.
