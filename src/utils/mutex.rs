use core::{
    cell::UnsafeCell,
    hint::spin_loop,
    marker::{Send, Sync},
    ops::{Deref, DerefMut, Drop},
    sync::atomic::{AtomicBool, Ordering},
};

pub struct SpinMutex<T> {
    inner: UnsafeCell<T>,
    lock: AtomicBool,
}

pub struct SpinMutexGuard<'a, T> {
    mutex: &'a SpinMutex<T>,
}

// mutex turns Send types into Send + Sync types
unsafe impl<T: Send> Send for SpinMutex<T> {}
unsafe impl<T: Send> Sync for SpinMutex<T> {}

impl<T> SpinMutex<T> {
    pub const fn new(data: T) -> Self {
        Self {
            inner: UnsafeCell::new(data),
            lock: AtomicBool::new(false),
        }
    }

    #[inline(always)]
    pub fn is_locked(&self) -> bool {
        self.lock.load(Ordering::Relaxed)
    }

    pub fn lock(&self) -> SpinMutexGuard<'_, T> {
        while self
            .lock
            .compare_exchange(false, true, Ordering::Acquire, Ordering::Relaxed)
            .is_err()
        {
            while self.is_locked() {
                spin_loop();
            }
        }

        SpinMutexGuard { mutex: self }
    }
}

impl<T> Deref for SpinMutexGuard<'_, T> {
    type Target = T;
    fn deref(&self) -> &T {
        unsafe { &*self.mutex.inner.get() }
    }
}

impl<T> DerefMut for SpinMutexGuard<'_, T> {
    fn deref_mut(&mut self) -> &mut T {
        unsafe { &mut *self.mutex.inner.get() }
    }
}

impl<T> Drop for SpinMutexGuard<'_, T> {
    fn drop(&mut self) {
        self.mutex.lock.store(false, Ordering::Release);
    }
}
