#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""
Unit and integration test suite for scripts/kernel-sloc.

This test harness verifies the CLI contract, tool dependency checks,
line counting logic, error handling, and JSON reporting for all modes
of the kernel-sloc helper script (files, tree, kernel, dwarf).

It is designed to run against both the shell implementation and future
pure Python implementations of kernel-sloc without test modifications.

The path to the binary under test can be overridden using the KERNEL_SLOC_BIN
environment variable:
    KERNEL_SLOC_BIN=./scripts/kernel-sloc python3 -m unittest
"""

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

DEFAULT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
KERNEL_SLOC_PATH = os.environ.get(
    "KERNEL_SLOC_BIN", os.path.join(DEFAULT_SCRIPT_DIR, "kernel-sloc")
)


class TestKernelSloc(unittest.TestCase):
    # pylint: disable=too-many-public-methods
    """Test suite for kernel-sloc."""

    def setUp(self):
        # pylint: disable=consider-using-with
        self.tempdir = tempfile.TemporaryDirectory()
        self.td = self.tempdir.name
        self.bin_dir = os.path.join(self.td, "bin")
        os.makedirs(self.bin_dir)
        self.env = os.environ.copy()
        # Prepend isolated bin_dir to PATH for mock tools
        self.env["PATH"] = f"{self.bin_dir}:{self.env.get('PATH', '')}"

    def tearDown(self):
        self.tempdir.cleanup()

    def make_executable(self, path, content):
        """Write content to path and make it executable."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IRUSR)
        return path

    def create_mock_cloc(self, fixed_sum=None):
        """Create a mock cloc executable.

        If fixed_sum is None, count lines in files or list-file.
        """
        script = f"""#!/usr/bin/env python3
import sys

files = []
fixed_sum = {repr(fixed_sum)}

i = 1
while i < len(sys.argv):
    arg = sys.argv[i]
    if arg.startswith("--list-file="):
        list_file = arg.split("=", 1)[1]
        with open(list_file, encoding="utf-8") as f:
            files.extend([line.strip() for line in f if line.strip()])
    elif not arg.startswith("--"):
        files.append(arg)
    i += 1

if fixed_sum is not None:
    total = fixed_sum
else:
    total = 0
    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                total += len([l for l in fp if l.strip()])
        except Exception:
            pass

print("files,language,blank,comment,code")
print(f"{{len(files)}},C,0,0,{{total}}")
print(f"SUM,SUM,0,0,{{total}}")
"""
        return self.make_executable(os.path.join(self.bin_dir, "cloc"), script)

    def run_sloc(self, args, env=None, check=False):
        """Execute kernel-sloc with specified arguments and environment."""
        run_env = self.env.copy()
        if env:
            run_env.update(env)
        res = subprocess.run(
            [KERNEL_SLOC_PATH] + args,
            env=run_env,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and res.returncode != 0:
            raise subprocess.CalledProcessError(
                res.returncode,
                [KERNEL_SLOC_PATH] + args,
                res.stdout,
                res.stderr,
            )
        return res

    # -------------------------------------------------------------------------
    # CLI Interface and Usage Validation
    # -------------------------------------------------------------------------

    def test_help_flags(self):
        """Test -h and --help print usage to stdout and exit successfully."""
        for flag in ["-h", "--help"]:
            res = self.run_sloc([flag])
            self.assertEqual(res.returncode, 0, f"Failed on {flag}")
            self.assertIn("Usage:", res.stdout)
            self.assertIn("kernel BUILD_DIR", res.stdout)
            self.assertIn("dwarf ELF", res.stdout)
            self.assertIn("tree DIR", res.stdout)
            self.assertIn("files FILE...", res.stdout)

    def test_invalid_arguments(self):
        """Test missing arguments or unknown modes exit with status 2."""
        # No arguments
        res = self.run_sloc([])
        self.assertEqual(res.returncode, 2)
        self.assertIn("Usage:", res.stderr)

        # Unrecognized mode
        res = self.run_sloc(["unknown_mode"])
        self.assertEqual(res.returncode, 2)
        self.assertIn("Usage:", res.stderr)

        # Extra unexpected argument with help flag
        res = self.run_sloc(["-h", "extra"])
        self.assertEqual(res.returncode, 2)

        # Missing report target
        res = self.run_sloc(["--report"])
        self.assertEqual(res.returncode, 2)

        # Report target starting with hyphen
        res = self.run_sloc(["--report", "-not_a_file", "tree", self.td])
        self.assertEqual(res.returncode, 2)

    def test_report_unsupported_modes(self):
        """Test that --report rejects tree and files modes with exit 1."""
        rep = os.path.join(self.td, "rep.json")

        res = self.run_sloc(["--report", rep, "tree", self.td])
        self.assertEqual(res.returncode, 1)
        self.assertIn(
            "--report supports only kernel and dwarf modes", res.stderr
        )

        test_file = os.path.join(self.td, "test.c")
        with open(test_file, "w", encoding="utf-8") as fp:
            fp.write("int x = 1;\n")
        res = self.run_sloc(["--report", rep, "files", test_file])
        self.assertEqual(res.returncode, 1)
        self.assertIn(
            "--report supports only kernel and dwarf modes", res.stderr
        )

    def test_missing_dependencies(self):
        """Test error reporting when required commands are absent in PATH."""
        clean_path = ":".join(
            p
            for p in os.environ.get("PATH", "").split(":")
            if p != self.bin_dir and not shutil.which("cloc", path=p)
        )
        res = self.run_sloc(["tree", self.td], env={"PATH": clean_path})
        self.assertEqual(res.returncode, 1)
        self.assertIn("required command not found: cloc", res.stderr)

    # -------------------------------------------------------------------------
    # Files Mode
    # -------------------------------------------------------------------------

    def test_files_mode_success(self):
        """Test files mode accurately counts specified source files."""
        self.create_mock_cloc()
        f1 = os.path.join(self.td, "f1.c")
        with open(f1, "w", encoding="utf-8") as fp:
            fp.write("int a;\nint b;\n")
        f2 = os.path.join(self.td, "f2.c")
        with open(f2, "w", encoding="utf-8") as fp:
            fp.write("int c;\n")

        res = self.run_sloc(["files", f1, f2])
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "3")
        self.assertIn("files: 2 path(s), 3 SLOC", res.stderr)

    def test_files_mode_errors(self):
        """Test files mode error handling for missing args and bad paths."""
        self.create_mock_cloc()

        # Missing file list
        res = self.run_sloc(["files"])
        self.assertEqual(res.returncode, 2)

        # Non-existent source file
        res = self.run_sloc(["files", os.path.join(self.td, "nonexistent.c")])
        self.assertEqual(res.returncode, 1)
        self.assertIn("source file not found", res.stderr)

        # File name containing newline
        bad_path = os.path.join(self.td, "bad\npath.c")
        with open(bad_path, "w", encoding="utf-8") as fp:
            fp.write("int x;\n")
        res = self.run_sloc(["files", bad_path])
        self.assertEqual(res.returncode, 1)
        self.assertIn("source paths must not contain newlines", res.stderr)

    # -------------------------------------------------------------------------
    # Tree Mode
    # -------------------------------------------------------------------------

    def test_tree_mode_success(self):
        """Test tree mode executes cloc and reports source tree count."""
        self.create_mock_cloc(fixed_sum=42)
        res = self.run_sloc(["tree", self.td])
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "42")
        self.assertIn(
            f"source tree {self.td} (C/C++ and headers): 42 SLOC", res.stderr
        )

    def test_tree_mode_errors(self):
        """Test tree mode errors on missing arg or non-existent path."""
        self.create_mock_cloc()

        # Missing target directory
        res = self.run_sloc(["tree"])
        self.assertEqual(res.returncode, 2)

        # Non-existent target directory
        res = self.run_sloc(["tree", os.path.join(self.td, "nonexistent_dir")])
        self.assertEqual(res.returncode, 1)
        self.assertIn("source dir not found", res.stderr)

    # -------------------------------------------------------------------------
    # Kernel Mode
    # -------------------------------------------------------------------------

    def test_kernel_mode_with_compile_commands(self):
        """Test kernel mode parses compile_commands.json and counts."""
        self.create_mock_cloc()
        build_dir = os.path.join(self.td, "kbuild")
        os.makedirs(build_dir)
        src1 = os.path.join(build_dir, "init.c")
        with open(src1, "w", encoding="utf-8") as fp:
            fp.write("int init(void) { return 0; }\n")
        src2 = os.path.join(build_dir, "main.c")
        with open(src2, "w", encoding="utf-8") as fp:
            fp.write("int main(void) { return 0; }\n")

        # Include src1 twice to verify deduplication
        ccj = os.path.join(build_dir, "compile_commands.json")
        with open(ccj, "w", encoding="utf-8") as fp:
            json.dump(
                [
                    {"directory": build_dir, "file": "init.c"},
                    {"directory": build_dir, "file": "init.c"},
                    {"directory": build_dir, "file": "main.c"},
                ],
                fp,
            )

        rep = os.path.join(self.td, "report.json")
        res = self.run_sloc(["--report", rep, "kernel", build_dir])
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "2")
        self.assertIn("kernel compiled sources: 2 files, 2 SLOC", res.stderr)

        self.assertTrue(os.path.exists(rep))
        with open(rep, encoding="utf-8") as fp:
            data = json.load(fp)
        self.assertEqual(data["mode"], "kernel")
        self.assertEqual(data["sloc"], 2)
        self.assertEqual(data["target"], os.path.abspath(build_dir))
        self.assertEqual(data["files"], sorted([src1, src2]))

    def test_kernel_mode_overwrite_protection(self):
        """Test kernel mode protects inputs from being overwritten."""
        self.create_mock_cloc()
        build_dir = os.path.join(self.td, "kbuild")
        os.makedirs(build_dir)
        src = os.path.join(build_dir, "init.c")
        with open(src, "w", encoding="utf-8") as fp:
            fp.write("int x = 1;\n")
        ccj = os.path.join(build_dir, "compile_commands.json")
        with open(ccj, "w", encoding="utf-8") as fp:
            json.dump([{"directory": build_dir, "file": "init.c"}], fp)

        # Attempt to overwrite compile_commands.json
        res = self.run_sloc(["--report", ccj, "kernel", build_dir])
        self.assertEqual(res.returncode, 1)
        self.assertIn("report must not overwrite a measured input", res.stderr)

        # Attempt to overwrite source file
        res = self.run_sloc(["--report", src, "kernel", build_dir])
        self.assertEqual(res.returncode, 1)
        self.assertIn("report must not overwrite a measured input", res.stderr)

    def test_kernel_mode_missing_source(self):
        """Test kernel mode dies when compiled source is missing on disk."""
        self.create_mock_cloc()
        build_dir = os.path.join(self.td, "kbuild")
        os.makedirs(build_dir)
        ccj = os.path.join(build_dir, "compile_commands.json")
        with open(ccj, "w", encoding="utf-8") as fp:
            json.dump([{"directory": build_dir, "file": "missing.c"}], fp)

        res = self.run_sloc(["kernel", build_dir])
        self.assertEqual(res.returncode, 1)
        self.assertIn("compiled source not found", res.stderr)

    def test_kernel_mode_empty_sources(self):
        """Test kernel mode dies when compile_commands.json has no sources."""
        self.create_mock_cloc()
        build_dir = os.path.join(self.td, "kbuild")
        os.makedirs(build_dir)
        ccj = os.path.join(build_dir, "compile_commands.json")
        with open(ccj, "w", encoding="utf-8") as fp:
            json.dump([], fp)

        res = self.run_sloc(["kernel", build_dir])
        self.assertEqual(res.returncode, 1)
        self.assertIn(
            "no compiled sources found (build the kernel first)", res.stderr
        )

    def test_kernel_mode_newline_in_source_path(self):
        """Test kernel mode rejects source paths containing newlines."""
        self.create_mock_cloc()
        build_dir = os.path.join(self.td, "kbuild")
        os.makedirs(build_dir)
        bad_src = os.path.join(build_dir, "bad\nfile.c")
        with open(bad_src, "w", encoding="utf-8") as fp:
            fp.write("int x;\n")
        ccj = os.path.join(build_dir, "compile_commands.json")
        with open(ccj, "w", encoding="utf-8") as fp:
            json.dump([{"directory": build_dir, "file": "bad\nfile.c"}], fp)

        res = self.run_sloc(["kernel", build_dir])
        self.assertEqual(res.returncode, 1)
        self.assertIn("source paths must not contain newlines", res.stderr)

    # -------------------------------------------------------------------------
    # DWARF Mode
    # -------------------------------------------------------------------------

    def test_dwarf_mode_mock_toolchain(self):
        """Test DWARF mode line address extraction and JSON report."""
        mock_objdump = os.path.join(self.bin_dir, "objdump")
        self.make_executable(
            mock_objdump,
            """#!/usr/bin/env python3
print("Decoded dump of debug contents of section .debug_line:")
print("File name   Line number    Starting address    View    Stmt")
print("foo.c                 1              0x1000               x")
print("foo.c                 2              0x1010               x")
print("bar.c                10              0x1020               x")
print("bar.c                10              0x1030               x")
""",
        )

        mock_addr2line = os.path.join(self.bin_dir, "addr2line")
        self.make_executable(
            mock_addr2line,
            """#!/usr/bin/env python3
import sys
with_func = "-f" in sys.argv
for line in sys.stdin:
    addr = line.strip()
    if with_func:
        if addr in ("0x1000", "0x1010"):
            print("foo_func")
            print(f"/mock/foo.c:{1 if addr == '0x1000' else 2}")
        elif addr == "0x1020":
            print("bar_func")
            print("/mock/bar.c:10 (discriminator 1)")
        elif addr == "0x1030":
            print("bar_func")
            print("/mock/bar.c:10")
        else:
            print("??")
            print("??:0")
    else:
        if addr == "0x1000":
            print("/mock/foo.c:1")
        elif addr == "0x1010":
            print("/mock/foo.c:2")
        elif addr in ("0x1020", "0x1030"):
            print("/mock/bar.c:10")
        else:
            print("??:0")
""",
        )

        dummy_elf = os.path.join(self.td, "test.elf")
        with open(dummy_elf, "w", encoding="utf-8") as fp:
            fp.write("dummy elf binary")

        rep = os.path.join(self.td, "dwarf_report.json")
        res = self.run_sloc(["--report", rep, "dwarf", dummy_elf])
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "3")
        self.assertIn(
            "dwarf distinct source lines (debug-info estimate): 3", res.stderr
        )

        with open(rep, encoding="utf-8") as fp:
            data = json.load(fp)
        self.assertEqual(data["mode"], "dwarf")
        self.assertEqual(data["sloc"], 3)
        self.assertEqual(len(data["source_lines"]), 3)
        self.assertEqual(len(data["functions"]), 2)

    def test_dwarf_mode_no_lines_error(self):
        """Test DWARF mode errors when no debug source lines are found."""
        mock_objdump = os.path.join(self.bin_dir, "objdump")
        self.make_executable(mock_objdump, "#!/usr/bin/env python3\npass\n")
        mock_addr2line = os.path.join(self.bin_dir, "addr2line")
        self.make_executable(mock_addr2line, "#!/usr/bin/env python3\npass\n")

        dummy_elf = os.path.join(self.td, "test.elf")
        with open(dummy_elf, "w", encoding="utf-8") as fp:
            fp.write("dummy elf binary")

        res = self.run_sloc(["dwarf", dummy_elf])
        self.assertEqual(res.returncode, 1)
        self.assertIn("no DWARF source lines found", res.stderr)

    def test_dwarf_mode_toolchain_prefix(self):
        """Test CROSS_COMPILE prefix selects prefixed binutils."""
        mock_cross_od = os.path.join(self.bin_dir, "myarch-objdump")
        self.make_executable(
            mock_cross_od,
            """#!/usr/bin/env python3
print("foo.c 1 0x2000 x")
""",
        )
        mock_cross_a2l = os.path.join(self.bin_dir, "myarch-addr2line")
        self.make_executable(
            mock_cross_a2l,
            """#!/usr/bin/env python3
import sys
for _ in sys.stdin:
    print("/mock/cross.c:1")
""",
        )

        dummy_elf = os.path.join(self.td, "test.elf")
        with open(dummy_elf, "w", encoding="utf-8") as fp:
            fp.write("dummy elf binary")

        res = self.run_sloc(
            ["dwarf", dummy_elf], env={"CROSS_COMPILE": "myarch-"}
        )
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "1")

    # -------------------------------------------------------------------------
    # End-to-End Integration (Real Toolchain)
    # -------------------------------------------------------------------------

    @unittest.skipUnless(
        shutil.which("gcc")
        and shutil.which("objdump")
        and shutil.which("addr2line"),
        "gcc, objdump, or addr2line not available on host",
    )
    def test_dwarf_mode_real_gcc(self):
        """Integration test: build real ELF with gcc -g and run DWARF sloc."""
        c_source = os.path.join(self.td, "sample.c")
        with open(c_source, "w", encoding="utf-8") as fp:
            fp.write(
                """int helper(int a) {
    return a * 2;
}
int main(void) {
    int val = helper(21);
    return val;
}
"""
            )
        elf_path = os.path.join(self.td, "sample.elf")
        subprocess.check_call(["gcc", "-g", "-O0", c_source, "-o", elf_path])

        rep = os.path.join(self.td, "real_dwarf.json")
        res = self.run_sloc(["--report", rep, "dwarf", elf_path])
        self.assertEqual(res.returncode, 0)
        count = int(res.stdout.strip())
        self.assertGreater(count, 0)
        self.assertIn("dwarf distinct source lines", res.stderr)

        with open(rep, encoding="utf-8") as fp:
            data = json.load(fp)
        self.assertEqual(data["mode"], "dwarf")
        self.assertEqual(data["sloc"], count)
        files = data["files"]
        self.assertTrue(any("sample.c" in f for f in files))
        funcs = {f["name"] for f in data["functions"]}
        self.assertIn("main", funcs)
        self.assertIn("helper", funcs)


if __name__ == "__main__":
    unittest.main()
