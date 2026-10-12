# Rust operating system on i686

## todo:  
- [x] gdt loading  
- [x] interrupts  
- [x] keyboard input (verified live: scancode received via IDT from ISO boot path)  
- [x] deterministic QEMU boot test (scripts/boot_test.py, 10/10 verified)  
- [x] Proxmox-ready ISO (dist/rosti.iso, GRUB multiboot, boot-verified in QEMU) — see PROXMOX.md  
- [ ] USE TYPES PROPERLY AND MAKE THINGS ACTUALLY WORK!!! <<<<  
- [ ] debug/test harness  
- [ ] paging  
- [x] shell Backspace visually erases characters, including wrapped input
  (QEMU ELF and ISO display regression verified; VM deployment pending)
- [ ] rtc?  

## Project goals  
Learn more about operating systems and attempt to reimplement (nearly) 
everything without working with external libraries, minus the Rust core and 
alloc libraries. 
