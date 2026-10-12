# Rust operating system on i686

## todo:  
- [x] gdt loading  
- [x] interrupts  
- [x] keyboard input (verified live: scancode received via IDT from ISO boot path)  
- [x] deterministic QEMU boot test (scripts/boot_test.py, 10/10 verified)  
- [x] Proxmox-ready ISO (dist/rosti.iso, GRUB multiboot, boot-verified in QEMU) — see PROXMOX.md  
- [ ] USE TYPES PROPERLY AND MAKE THINGS ACTUALLY WORK!!! <<<<  
- [x] regression/deployment harness (49 host tests; 25 deployment gates)
- [x] physical frames and identity paging (active on 512 MiB VM 103; null guard and CPU faults verified)
- [x] shell Backspace visually erases characters, including wrapped input
  (QEMU ELF/ISO and live Proxmox VM 103 display regression verified)
- [ ] rtc?  

## Project goals  
Learn more about operating systems and attempt to reimplement (nearly) 
everything without working with external libraries, minus the Rust core and 
alloc libraries. 
