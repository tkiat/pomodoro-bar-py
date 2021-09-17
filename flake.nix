{
  description = "A feature-rich CLI-based Pomorodo clock with optional integration with external displays: currently polybar and xmobar.";
  inputs = { nixpkgs.url = "github:NixOS/nixpkgs/nixos-21.11"; };

  outputs = { self, nixpkgs }:
    let pkg-name = "pomodoro-bar-py";
    in
    {
    defaultPackage.x86_64-linux =
      with import nixpkgs { system = "x86_64-linux"; };
      stdenv.mkDerivation {
        name = pkg-name;
        src = self;
        buildInputs = [
          (python39.withPackages (ps: with ps; [ pyxdg ]))
        ];
        unpackPhase = "true";
        installPhase = ''
          mkdir -p $out/bin
          cp $src/pomodoro_bar.py $out/bin/$name
          chmod +x $out/bin/$name
        '';
      };

    devShell.x86_64-linux =
      with import nixpkgs { system = "x86_64-linux"; };
      pkgs.mkShell {
        buildInputs = [
          nixpkgs-fmt
          (python39.withPackages (ps: with ps; [ pyxdg yapf ]))
          pyright
        ];
        shellHook = ''
          export PS1="\e[01;32mnix-develop\e[m\e[01;31m (${pkg-name})\e[m\$ "
        '';
      };
  };
}
