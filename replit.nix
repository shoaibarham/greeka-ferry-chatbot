{pkgs}: {
  deps = [
    pkgs.jq
    pkgs.sqlite
    pkgs.libxcrypt
    pkgs.bash
    pkgs.postgresql
    pkgs.openssl
  ];
}
