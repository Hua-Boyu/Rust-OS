mod support;
fn main() {
    if let Err(e) = support::run("rostifs-inspect") {
        eprintln!("rostifs-inspect: {e}");
        std::process::exit(1);
    }
}
