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



@register_tool("query_u")
class QueryUTool:

    async def run(self, input_data: dict):

        x = float(input_data.get("x"))
        t = float(input_data.get("t"))

        model = PINN()
        model.load_state_dict(torch.load("heat1d.pt", map_location="cpu"))
        model.eval()

        with torch.no_grad():
            u = model(
                torch.tensor([[x]], dtype=torch.float32),
                torch.tensor([[t]], dtype=torch.float32)
            )

        return {
            "tool": "query_u",
            "input": {
                "x": x,
                "t": t
            },
            "u": float(u.item())
        }