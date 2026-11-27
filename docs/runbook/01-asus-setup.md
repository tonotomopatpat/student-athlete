# 01 Set up the ASUS and run `doctor`

## 1. What and why

Prepare the ASUS TUF 15 (RTX 3050) for training and confirm PyTorch sees the GPU. All later training runs happen on this machine.

## 2. Before you start

- The latest code is pushed from the Mac (`git push`), so the ASUS can pull it.
- About 60 GB free disk on the drive that will hold the repo.
- Choose the system: Ubuntu 24.04 (dual boot, recommended: faster and more stable for long runs) or Windows 11 with WSL2 (Ubuntu inside Windows). Everything below runs in an Ubuntu terminal either way.

## 3. Commands

NVIDIA driver:

- Ubuntu: `sudo ubuntu-drivers install`, then reboot.
- WSL2: install the latest NVIDIA Game Ready or Studio driver in Windows. Do not install a Linux driver inside WSL.

Check it: `nvidia-smi` must list the RTX 3050.

Python and the repo:

```bash
sudo apt update && sudo apt install -y git python3.12 python3.12-venv build-essential
git clone <your repo URL> sideline && cd sideline/backend
python3.12 -m venv .venv-train
source .venv-train/bin/activate
pip install --upgrade pip
pip install -r requirements-train.txt
python -m app.lm doctor
```

In WSL2, keep the repo inside the Linux home folder (`~/sideline`), not under `/mnt/c`, or disk reads will be very slow.

Power settings (do once):

- Armoury Crate (Windows) or the power menu (Ubuntu): Performance or Turbo mode.
- Turn off sleep while plugged in. In Windows, pause updates during training weeks.
- Plugged in, on a cooling pad, lid open.

## 4. How long

1 to 2 hours, mostly downloads (PyTorch with CUDA is about 3 GB).

## 5. What you should see

`doctor` prints one line per check, for example:

```
[OK  ] GPU            NVIDIA GeForce RTX 3050 Laptop GPU
[OK  ] GPU memory     4.3 GB
[OK  ] bfloat16       yes
[OK  ] Speed test     9.5 TFLOPS (bfloat16 on cuda)
Ready to train on cuda.
```

## 6. How to check it worked

The last line says `Ready to train on cuda.` and no line says `FAIL`.

## 7. If it fails

- `GPU  none found`: the driver is missing or PyTorch is the CPU build. Run `nvidia-smi`. If that works, run `python -c "import torch; print(torch.version.cuda)"`; if it prints `None`, reinstall PyTorch with the command from the official selector (pytorch.org, Linux, pip, CUDA 12.x), then `pip install -r requirements-train.txt` again.
- `bfloat16  no`: training still works but slower and in float32. Send the output; the agent will adjust the configs.
- `Free disk` warning: free space or move the repo to a bigger drive before card 02.
- `missing: pip install ...`: the environment is not active. Run `source .venv-train/bin/activate`.

## 8. What to send back

The full `doctor` output (about 12 lines), and whether you chose Ubuntu or WSL2.
