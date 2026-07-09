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

@register_tool("train_heat_1d")
class TrainHeat1DTool:

    async def run(self, input_data: dict):

        alpha = float(input_data.get("alpha", 1.0))
        epochs = int(input_data.get("epochs", 5000))

        model = PINN()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

        for epoch in range(epochs):

            N_f, N_ic, N_bc = 2000, 200, 200

            x_f = torch.rand((N_f, 1))
            t_f = torch.rand((N_f, 1))

            x_ic = torch.rand((N_ic, 1))
            t_ic = torch.zeros_like(x_ic)

            t_bc = torch.rand((N_bc, 1))
            x_bc0 = torch.zeros_like(t_bc)
            x_bc1 = torch.ones_like(t_bc)

            # PDE loss
            L_pde = pde_loss(model, x_f, t_f, alpha)

            # Initial condition loss
            u_ic_pred = model(x_ic, t_ic)
            u_ic_true = torch.sin(torch.pi * x_ic)
            L_ic = torch.mean((u_ic_pred - u_ic_true) ** 2)

            # Boundary condition loss
            u_bc0 = model(x_bc0, t_bc)
            u_bc1 = model(x_bc1, t_bc)
            L_bc = torch.mean(u_bc0 ** 2) + torch.mean(u_bc1 ** 2)

            # Total loss
            loss = L_pde + 50 * L_ic + 10 * L_bc

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            if epoch % 500 == 0:
                print(
                    f"[train_heat_1d] "
                    f"epoch={epoch}, "
                    f"loss={loss.item():.6f}, "
                    f"L_pde={L_pde.item():.6f}, "
                    f"L_ic={L_ic.item():.6f}, "
                    f"L_bc={L_bc.item():.6f}"
                )
        #print("123")
        torch.save(model.state_dict(), "heat1d.pt")
        #print("456")
        return {
            "tool": "train_heat_1d",
            "alpha": alpha,
            "epochs": epochs,
            "model_path": "heat1d.pt",
            "final_loss": float(loss.item()),
            "status": "trained"
        }
        
