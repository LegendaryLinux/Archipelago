import os
import shutil
import sys
import sysconfig
from pathlib import Path
from hashlib import sha3_512
import base64
import datetime
from Utils import version_tuple
from collections.abc import Iterable
import typing
import setuptools
from Launcher import components, icon_paths


# This is a bit jank. We need cx-Freeze to be able to run anything from this script, so install it
import subprocess
import pkg_resources
requirement = 'cx-Freeze>=6.9'
try:
    pkg_resources.require(requirement)
    import cx_Freeze
except pkg_resources.ResolutionError:
    if '--yes' not in sys.argv and '-y' not in sys.argv:
        input(f'Requirement {requirement} is not satisfied, press enter to install it')
    subprocess.call([sys.executable, '-m', 'pip', 'install', requirement, '--upgrade'])
    import cx_Freeze


if os.path.exists("X:/pw.txt"):
    print("Using signtool")
    with open("X:/pw.txt") as f:
        pw = f.read()
    signtool = r'signtool sign /f X:/_SITS_Zertifikat_.pfx /p ' + pw + r' /fd sha256 /tr http://timestamp.digicert.com/ '
else:
    signtool = None


arch_folder = "exe.{platform}-{version}".format(platform=sysconfig.get_platform(),
                                                version=sysconfig.get_python_version())
buildfolder = Path("build", arch_folder)
is_windows = sys.platform in ("win32", "cygwin", "msys")


# see Launcher.py on how to add scripts to setup.py
exes = [
    cx_Freeze.Executable(
        script=f'{c.script_name}.py',
        target_name=c.frozen_name + (".exe" if is_windows else ""),
        icon=icon_paths[c.icon],
        base="Win32GUI" if is_windows and not c.cli else None
    ) for c in components if c.script_name
]

extra_data = ["LICENSE", "data", "EnemizerCLI", "host.yaml", "SNI"]


def remove_sprites_from_folder(folder):
    for file in os.listdir(folder):
        if file != ".gitignore":
            os.remove(folder / file)


def _threaded_hash(filepath):
    hasher = sha3_512()
    hasher.update(open(filepath, "rb").read())
    return base64.b85encode(hasher.digest()).decode()


# cx_Freeze's build command runs other commands. Override to accept --yes and store that.
class BuildCommand(cx_Freeze.dist.build):
    user_options = [
        ('yes', 'y', 'Answer "yes" to all questions.'),
    ]
    yes: bool
    last_yes: bool = False  # used by sub commands of build

    def initialize_options(self):
        super().initialize_options()
        type(self).last_yes = self.yes = False

    def finalize_options(self):
        super().finalize_options()
        type(self).last_yes = self.yes


# Override cx_Freeze's build_exe command for pre and post build steps
class BuildExeCommand(cx_Freeze.dist.build_exe):
    user_options = cx_Freeze.dist.build_exe.user_options + [
        ('yes', 'y', 'Answer "yes" to all questions.'),
        ('extra-data=', None, 'Additional files to add.'),
    ]
    yes: bool
    extra_data: Iterable  # [any] not available in 3.8

    buildfolder: Path
    libfolder: Path
    library: Path
    buildtime: datetime.datetime

    def initialize_options(self):
        super().initialize_options()
        self.yes = BuildCommand.last_yes
        self.extra_data = []

    def finalize_options(self):
        super().finalize_options()
        self.buildfolder = self.build_exe
        self.libfolder = Path(self.buildfolder, "lib")
        self.library = Path(self.libfolder, "library.zip")

    def installfile(self, path, keep_content=False):
        folder = self.buildfolder
        print('copying', path, '->', folder)
        if path.is_dir():
            folder /= path.name
            if folder.is_dir() and not keep_content:
                shutil.rmtree(folder)
            shutil.copytree(path, folder, dirs_exist_ok=True)
        elif path.is_file():
            shutil.copy(path, folder)
        else:
            print('Warning,', path, 'not found')

    def create_manifest(self, create_hashes=False):
        # Since the setup is now split into components and the manifest is not,
        # it makes most sense to just remove the hashes for now. Not aware of anyone using them.
        hashes = {}
        manifestpath = os.path.join(self.buildfolder, "manifest.json")
        if create_hashes:
            from concurrent.futures import ThreadPoolExecutor
            pool = ThreadPoolExecutor()
            for dirpath, dirnames, filenames in os.walk(self.buildfolder):
                for filename in filenames:
                    path = os.path.join(dirpath, filename)
                    hashes[os.path.relpath(path, start=self.buildfolder)] = pool.submit(_threaded_hash, path)

        import json
        manifest = {
            "buildtime": self.buildtime.isoformat(sep=" ", timespec="seconds"),
            "hashes": {path: hash.result() for path, hash in hashes.items()},
            "version": version_tuple}

        json.dump(manifest, open(manifestpath, "wt"), indent=4)
        print("Created Manifest")

    def run(self):
        # pre build steps
        print(f"Outputting to: {self.buildfolder}")
        os.makedirs(self.buildfolder, exist_ok=True)
        import ModuleUpdate
        ModuleUpdate.requirements_files.add(os.path.join("WebHostLib", "requirements.txt"))
        ModuleUpdate.update(yes=self.yes)

        # regular cx build
        self.buildtime = datetime.datetime.utcnow()
        super().run()

        # post build steps
        if sys.platform == "win32":  # kivy_deps is win32 only, linux picks them up automatically
            from kivy_deps import sdl2, glew
            for folder in sdl2.dep_bins + glew.dep_bins:
                shutil.copytree(folder, self.libfolder, dirs_exist_ok=True)
                print('copying', folder, '->', self.libfolder)

        for data in self.extra_data:
            self.installfile(Path(data))

        os.makedirs(self.buildfolder / "Players" / "Templates", exist_ok=True)
        from WebHostLib.options import create
        create()
        from worlds.AutoWorld import AutoWorldRegister
        for worldname, worldtype in AutoWorldRegister.world_types.items():
            if not worldtype.hidden:
                file_name = worldname+".yaml"
                shutil.copyfile(os.path.join("WebHostLib", "static", "generated", "configs", file_name),
                                self.buildfolder / "Players" / "Templates" / file_name)
        shutil.copyfile("meta.yaml", self.buildfolder / "Players" / "Templates" / "meta.yaml")

        try:
            from maseya import z3pr
        except ImportError:
            print("Maseya Palette Shuffle not found, skipping data files.")
            z3pr = None
        else:
            # maseya Palette Shuffle exists and needs its data files
            print("Maseya Palette Shuffle found, including data files...")
            file = z3pr.__file__
            self.installfile(Path(os.path.dirname(file)) / "data", keep_content=True)

        if signtool:
            for exe in self.distribution.executables:
                print(f"Signing {exe.target_name}")
                os.system(signtool + os.path.join(self.buildfolder, exe.target_name))
            print(f"Signing SNI")
            os.system(signtool + os.path.join(self.buildfolder, "SNI", "SNI.exe"))
            print(f"Signing OoT Utils")
            for exe_path in (("Compress", "Compress.exe"), ("Decompress", "Decompress.exe")):
                os.system(signtool + os.path.join(self.buildfolder, "lib", "worlds", "oot", "data", *exe_path))

        remove_sprites_from_folder(self.buildfolder / "data" / "sprites" / "alttpr")

        self.create_manifest()

        if is_windows:
            with open("setup.ini", "w") as f:
                min_supported_windows = "6.2.9200" if sys.version_info > (3, 9) else "6.0.6000"
                f.write(f"[Data]\nsource_path={self.buildfolder}\nmin_windows={min_supported_windows}\n")
        else:
            # make sure extra programs are executable
            enemizer_exe = self.buildfolder / 'EnemizerCLI/EnemizerCLI.Core'
            sni_exe = self.buildfolder / 'SNI/sni'
            extra_exes = (enemizer_exe, sni_exe)
            for extra_exe in extra_exes:
                if extra_exe.is_file():
                    extra_exe.chmod(0o755)
            # rewrite windows-specific things in host.yaml
            host_yaml = self.buildfolder / 'host.yaml'
            with host_yaml.open('r+b') as f:
                data = f.read()
                data = data.replace(b'EnemizerCLI.Core.exe', b'EnemizerCLI.Core')
                data = data.replace(b'factorio\\\\bin\\\\x64\\\\factorio', b'factorio/bin/x64/factorio')
                f.seek(0, os.SEEK_SET)
                f.write(data)
                f.truncate()


class AppImageCommand(setuptools.Command):
    description = "build an app image from build output"
    user_options = [
        ("build-folder=", None, "Folder to convert to AppImage."),
        ("dist-file=", None, "AppImage output file."),
        ("app-dir=", None, "Folder to use for packaging."),
        ("app-icon=", None, "The icon to use for the AppImage."),
        ("app-exec=", None, "The application to run inside the image."),
        ("yes", "y", 'Answer "yes" to all questions.'),
    ]
    build_folder: typing.Optional[Path]
    dist_file: typing.Optional[Path]
    app_dir: typing.Optional[Path]
    app_name: str
    app_exec: typing.Optional[Path]
    app_icon: typing.Optional[Path]  # source file
    app_id: str  # lower case name, used for icon and .desktop
    yes: bool

    def write_desktop(self):
        desktop_filename = self.app_dir / f'{self.app_id}.desktop'
        with open(desktop_filename, 'w', encoding="utf-8") as f:
            f.write("\n".join((
                "[Desktop Entry]",
                f'Name={self.app_name}',
                f'Exec={self.app_exec}',
                "Type=Application",
                "Categories=Game",
                f'Icon={self.app_id}',
                ''
            )))
        desktop_filename.chmod(0o755)

    def write_launcher(self, default_exe: Path):
        launcher_filename = self.app_dir / f'AppRun'
        with open(launcher_filename, 'w', encoding="utf-8") as f:
            f.write(f"""#!/bin/sh
exe="{default_exe}"
match="${{1#--executable=}}"
if [ "${{#match}}" -lt "${{#1}}" ]; then
    exe="$match"
    shift
elif [ "$1" == "-executable" ] || [ "$1" == "--executable" ]; then
    exe="$2"
    shift; shift
fi
tmp="${{exe#*/}}"
if [ ! "${{#tmp}}" -lt "${{#exe}}" ]; then
    exe="{default_exe.parent}/$exe"
fi
$APPDIR/$exe "$@"
""")
        launcher_filename.chmod(0o755)

    def install_icon(self, src: Path, name: typing.Optional[str] = None, symlink: typing.Optional[Path] = None):
        try:
            from PIL import Image
        except ModuleNotFoundError:
            if not self.yes:
                input(f'Requirement PIL is not satisfied, press enter to install it')
            subprocess.call([sys.executable, '-m', 'pip', 'install', 'Pillow', '--upgrade'])
            from PIL import Image
        im = Image.open(src)
        res, _ = im.size

        if not name:
            name = src.stem
        ext = src.suffix
        dest_dir = Path(self.app_dir / f'usr/share/icons/hicolor/{res}x{res}/apps')
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f'{name}{ext}'
        shutil.copy(src, dest_file)
        if symlink:
            symlink.symlink_to(dest_file.relative_to(symlink.parent))

    def initialize_options(self):
        self.build_folder = None
        self.app_dir = None
        self.app_name = self.distribution.metadata.name
        self.app_icon = self.distribution.executables[0].icon
        self.app_exec = Path('opt/{app_name}/{exe}'.format(
            app_name=self.distribution.metadata.name, exe=self.distribution.executables[0].target_name
        ))
        self.dist_file = Path("dist", "{app_name}_{app_version}_{platform}.AppImage".format(
            app_name=self.distribution.metadata.name, app_version=self.distribution.metadata.version,
            platform=sysconfig.get_platform()
        ))
        self.yes = False

    def finalize_options(self):
        if not self.app_dir:
            self.app_dir = self.build_folder.parent / "AppDir"
        self.app_id = self.app_name.lower()

    def run(self):
        self.dist_file.parent.mkdir(parents=True, exist_ok=True)
        if self.app_dir.is_dir():
            shutil.rmtree(self.app_dir)
        self.app_dir.mkdir(parents=True)
        opt_dir = self.app_dir / "opt" / self.distribution.metadata.name
        shutil.copytree(self.build_folder, opt_dir)
        root_icon = self.app_dir / f'{self.app_id}{self.app_icon.suffix}'
        self.install_icon(self.app_icon, self.app_id, symlink=root_icon)
        shutil.copy(root_icon, self.app_dir / '.DirIcon')
        self.write_desktop()
        self.write_launcher(self.app_exec)
        print(f'{self.app_dir} -> {self.dist_file}')
        subprocess.call(f'./appimagetool -n "{self.app_dir}" "{self.dist_file}"', shell=True)


cx_Freeze.setup(
    name="Archipelago",
    version=f"{version_tuple.major}.{version_tuple.minor}.{version_tuple.build}",
    description="Archipelago",
    executables=exes,
    options={
        "build_exe": {
            "packages": ["websockets", "worlds", "kivy"],
            "includes": [],
            "excludes": ["numpy", "Cython", "PySide2", "PIL",
                         "pandas"],
            "zip_include_packages": ["*"],
            "zip_exclude_packages": ["worlds", "kivy"],
            "include_files": [],
            "include_msvcr": False,
            "replace_paths": [("*", "")],
            "optimize": 1,
            "build_exe": buildfolder,
            "extra_data": extra_data,
            "bin_includes": [] if is_windows else ["libffi.so"]
        },
        "bdist_appimage": {
           "build_folder": buildfolder,
        },
    },
    # override commands to get custom stuff in
    cmdclass={
        "build": BuildCommand,
        "build_exe": BuildExeCommand,
        "bdist_appimage": AppImageCommand,
    },
)
