@echo off
REM Launcher for AnimeVault Python commands.
REM The project .venv is broken (its base python.exe was removed).  C:\Python314
REM is a bare interpreter: it has no stdlib of its own and cannot locate its
REM DLLs unless its own directory is on PATH.  PYTHONPATH supplies the real
REM stdlib, the venv's site-packages (PySide6, pytest) and the project src.
REM PYTHONHOME is deliberately NOT set: it disables site-packages processing.
set "PATH=C:\Python314;%PATH%"
set "PYTHONPATH=C:\Users\Rudy0senpai\AppData\Local\Programs\Python\Python314\Lib;C:\Users\Rudy0senpai\T450\goto\git\AniListVault\src;C:\Users\Rudy0senpai\T450\goto\git\AniListVault\.venv\Lib\site-packages"
C:\Python314\python.exe %*