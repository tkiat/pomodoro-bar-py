# pomodoro-bar-py

This is a single Python script equivalent to [pomodoro-bar](https://github.com/tkiat/pomodoro-bar). Visit there for usage information.

## Prerequisites

- Linux (I don't have Windows and OS X to test it)
<!-- - pyxdg (optional, included with Nix installation option) -->

## Installation Options

1. Run the script directly
    ```bash
    $ git clone https://github.com/tkiat/pomodoro-bar-py.git
    $ cd pomodoro-bar-py/
    $ chmod +x pomodoro-bar.py
    $ ./pomodoro-bar.py -h
    ```
1. Using Nix
    ```bash
    $ git clone https://github.com/tkiat/pomodoro-bar-py.git
    $ cd pomodoro-bar-py/
    $ nix-build
    $ nix-env -i ./result
    $ pomodoro-bar-py -h
    ```
1. Using Nix Flakes (experimental)
    ```bash
    $ nix build github:tkiat/pomodoro-bar-py --out-link pomodoro-bar-py-result && nix-env -i ./pomodoro-bar-py-result
    ```
