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

@register_tool("compute_error")
class ComputeErrorTool:

    async def run(self, input_data: dict):

        alpha = float(input_data.get("alpha", 1.0))

        # Load model
        model = PINN()
        model.load_state_dict(torch.load("heat1d.pt", map_location="cpu"))
        model.eval()

        # Generate evaluation points
        x = torch.linspace(0, 1, 100).reshape(-1, 1)
        t = torch.linspace(0, 1, 100).reshape(-1, 1)

        X, T = torch.meshgrid(
            x.squeeze(),
            t.squeeze(),
            indexing="ij"
        )

        X = X.reshape(-1, 1)
        T = T.reshape(-1, 1)

        # Prediction
        with torch.no_grad():
            u_pred = model(X, T)
            u_true = exact_solution(X, T, alpha)

        # L2 Error
        error = torch.sqrt(torch.mean((u_pred - u_true) ** 2))

        return {
            "tool": "compute_error",
            "status": "success",
            "input": {
                "alpha": alpha
            },
            "output": {
                "L2_error": float(error.item())
            }
        }