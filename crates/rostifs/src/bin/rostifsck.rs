mod support;
fn main() {
    if let Err(e) = support::run("rostifsck") {
        eprintln!("rostifsck: {e}");
        std::process::exit(1);
    }
}
