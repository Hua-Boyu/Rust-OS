use crate::utils::mutex::SpinMutex;

const BUFFER_WIDTH: usize = 80;
const BUFFER_HEIGHT: usize = 25;
const BUFFER_LOCATION: *mut u16 = 0xb8000 as *mut u16;

#[allow(dead_code)]
pub enum Colours {
    Black = 0,
    Blue = 1,
    Green = 2,
    Cyan = 3,
    Red = 4,
    Magenta = 5,
    Brown = 6,
    LightGrey = 7,
    DarkGrey = 8,
    LightBlue = 9,
    LightGreen = 10,
    LightCyan = 11,
    LightRed = 12,
    LightMagenta = 13,
    LightBrown = 14,
    White = 15,
}

#[inline]
fn rec_colour(foreground: Colours, background: Colours) -> u8 {
    (background as u8) << 4 | foreground as u8
}

#[inline]
fn rec_entry(ch: u8, colour: u8) -> u16 {
    u16::from(colour) << 8 | u16::from(ch)
}

#[inline]
fn get_offset(row: usize, col: usize) -> usize {
    row * BUFFER_WIDTH + col
}

pub struct TermWriter {
    row: usize,
    col: usize,
    colour: u8,
}

impl TermWriter {
    const fn new() -> Self {
        Self {
            row: BUFFER_HEIGHT - 1,
            col: 0,
            colour: 0,
        }
    }

    fn clear_row(&mut self, row: usize) {
        for i in 0..BUFFER_WIDTH {
            unsafe {
                BUFFER_LOCATION
                    .add(get_offset(row, i))
                    .write_volatile(rec_entry(b' ', self.colour));
            }
        }
    }

    fn clear(&mut self) {
        for i in 0..(BUFFER_WIDTH * BUFFER_HEIGHT) {
            unsafe {
                BUFFER_LOCATION
                    .add(i)
                    .write_volatile(rec_entry(b' ', self.colour));
            }
        }

        self.row = BUFFER_HEIGHT - 1;
        self.col = 0;
    }

    fn new_line(&mut self) {
        // copy lines upward
        for r in 1..=self.row {
            for c in 0..BUFFER_WIDTH {
                unsafe {
                    let ch = BUFFER_LOCATION.add(get_offset(r, c)).read_volatile();
                    BUFFER_LOCATION.add(get_offset(r - 1, c)).write_volatile(ch);
                }
            }
        }
        self.clear_row(self.row);
        self.col = 0;
    }

    #[allow(dead_code)]
    fn set_colour(&mut self, foreground: Colours, background: Colours) {
        self.colour = rec_colour(foreground, background);
    }

    fn write_char(&mut self, ch: u8) {
        if ch == b'\n' {
            self.new_line();
            return;
        }

        if self.col >= BUFFER_WIDTH {
            self.new_line();
        }

        unsafe {
            BUFFER_LOCATION
                .add(get_offset(self.row, self.col))
                .write_volatile(rec_entry(ch, self.colour));
        }

        self.col += 1;
    }
}

impl core::fmt::Write for TermWriter {
    fn write_str(&mut self, s: &str) -> core::fmt::Result {
        for ch in s.bytes() {
            self.write_char(ch);
        }
        Ok(())
    }
}

pub static WRITER: SpinMutex<TermWriter> = SpinMutex::new(TermWriter::new());

pub fn init_writer() {
    let mut guard = WRITER.lock();
    guard.set_colour(Colours::White, Colours::Black);
    guard.clear();
}

pub fn clear_console() {
    WRITER.lock().clear();
}

#[doc(hidden)]
pub fn print_(args: core::fmt::Arguments) {
    use core::fmt::Write;
    WRITER.lock().write_fmt(args).unwrap();
}

#[macro_export]
macro_rules! print {
    ($($arg:tt)*) => ($crate::io::vga::print_(format_args!($($arg)*)));
}

#[macro_export]
macro_rules! println {
    () => ($crate::print!("\n"));
    ($($arg:tt)*) => ($crate::print!("{}\n", format_args!($($arg)*)));
}
