mod support;
fn main() {
    if let Err(e) = support::run("mkrostifs") {
        eprintln!("mkrostifs: {e}");
        std::process::exit(1);
    }
}
