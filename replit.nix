{pkgs}: {
  deps = [
    pkgs.sqlite
    pkgs.libxcrypt
    pkgs.bash
    pkgs.postgresql
    pkgs.openssl
  ];
}
