pub trait CanManipulateBits {
    fn create_mask(shift_left: Self, len: Self) -> Self;
    fn get_bits(&self, shift_left: Self, len: Self) -> Self;
    fn set_bits(&self, shift_left: Self, val: Self, len: Self) -> Self;
    fn set_one_bit(&self, shift_left: Self, enable: bool) -> Self;
}

macro_rules! impl_bit_manipulation {
    ($t:ty) => {
        impl CanManipulateBits for $t {
            #[inline]
            fn create_mask(shift_left: Self, len: Self) -> Self {
                // (1 << len) overflows when len == bit width; handle the
                // full-width case explicitly.
                let mask = if len == (core::mem::size_of::<Self>() * 8) as Self {
                    !0 as Self
                } else {
                    (1 << len) - 1
                };
                mask << shift_left
            }

            #[inline]
            fn get_bits(&self, shift_left: Self, len: Self) -> Self {
                (*self >> shift_left) & Self::create_mask(0, len)
            }

            #[inline]
            fn set_bits(&self, shift_left: Self, len: Self, val: Self) -> Self {
                let mask = Self::create_mask(shift_left, len);
                (*self & !mask) | ((val << shift_left) & mask)
            }

            #[inline]
            fn set_one_bit(&self, shift_left: Self, enable: bool) -> Self {
                self.set_bits(shift_left, enable as Self, 1)
            }
        }
    };
}

impl_bit_manipulation!(u8);
impl_bit_manipulation!(u16);
impl_bit_manipulation!(u32);
impl_bit_manipulation!(u64);
