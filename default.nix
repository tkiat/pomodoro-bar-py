{}:

let
  sources = import ./nix/sources.nix;
  pkgs = import sources.nixpkgs { };

  shell = pkgs.mkShell
    {
      buildInputs = [
        (pkgs.python39.withPackages (ps: with ps; [ pyxdg ]))
      ];
    };
in
pkgs.stdenv.mkDerivation {
  name = "pomodoro-bar-py";

  src = ./.;

  buildInputs = [
    (pkgs.python39.withPackages (ps: with ps; [ pyxdg ]))
  ];

  unpackPhase = "true";

  installPhase = ''
    mkdir -p $out/bin
    cp $src/pomodoro_bar.py $out/bin/$name
    chmod +x $out/bin/$name
  '';

  inherit shell;
}
