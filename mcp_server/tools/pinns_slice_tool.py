import datetime
import pandas as pd
from typing import Dict, Any
import torch
import torch.nn as nn
import numpy as np
import json
import matplotlib.pyplot as plt
import io
import base64
from mcp_server.registry import register_tool

# =========================
# Model
# =========================
class PINN(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(2, 128),
            nn.Tanh(),
            nn.Linear(128, 128),
            nn.Tanh(),
            nn.Linear(128, 1)
        )

    def forward(self, x, t):
        return self.net(torch.cat([x, t], dim=1))


# =========================
# PDE Loss
# =========================
def pde_loss(model, x, t, alpha):
    x.requires_grad_(True)
    t.requires_grad_(True)

    u = model(x, t)

    u_t = torch.autograd.grad(u, t, torch.ones_like(u), create_graph=True)[0]
    u_x = torch.autograd.grad(u, x, torch.ones_like(u), create_graph=True)[0]
    u_xx = torch.autograd.grad(u_x, x, torch.ones_like(u_x), create_graph=True)[0]

    return ((u_t - alpha * u_xx) ** 2).mean()


# =========================
# Exact solution
# =========================
def exact_solution(x, t, alpha):
    return torch.exp(-alpha * np.pi**2 * t) * torch.sin(np.pi * x)

@register_tool("slice_t")
class SliceTTool:

    async def run(self, input_data: dict):

        t = float(input_data.get("t"))
        n = int(input_data.get("n", 100))
        save_path = input_data.get("save_path", "slice.json")

        model = PINN()
        model.load_state_dict(torch.load("heat1d.pt", map_location="cpu"))
        model.eval()

        xs = torch.linspace(0, 1, n).reshape(-1, 1)
        ts = torch.full_like(xs, t)

        with torch.no_grad():
            u = model(xs, ts)

        x_list = xs.squeeze().tolist()
        u_list = u.squeeze().tolist()

        data = {
            "t": t,
            "x": x_list,
            "u": u_list
        }

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return {
            "tool": "slice_t",
            "status": "ok",
            "input": {
                "t": t,
                "n": n,
                "save_path": save_path
            },
            "json_file": save_path
        }