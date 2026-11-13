
# WIC2005 Programmable Network — Netlab

This repository contains my laboratory exercises and assignments for WIC2005 Programmable Network.

## Week 6 — Overlay Your Own Data Centre

I designed and tested a multi-tenant VXLAN network using Mininet, Linux bridges and VXLAN interfaces.

### Network Design

- Underlay network: 10.65.0.0/24
- Hypervisors: hv1, hv2 and hv3
- Sales tenant: VNI 165, three VMs across three hypervisors
- HR tenant: VNI 265, two VMs across two hypervisors
- Both tenants use the overlapping subnet 10.65.60.0/24
- Final configuration: 1500-byte underlay MTU and 1450-byte tenant MTU

### Experiments

I tested VXLAN connectivity, flood-and-learn behaviour, tenant isolation, an MTU black hole and two MTU solutions.

My TCP throughput measurements were:

- Black-hole configuration: 0 bits/sec
- Fix A (tenant MTU 1450): 4.01 Gbits/sec
- Fix B (underlay MTU 9000): 4.04 Gbits/sec

The supporting evidence is stored in the `evidence6/` directory.

### AI Usage Declaration — Level 3 (Open)

I used ChatGPT (OpenAI) as an AI learning assistant during this assignment.

ChatGPT helped me understand VXLAN concepts, interpret Mininet and networking test results, troubleshoot configuration issues, plan testing steps, and draft and improve my technical explanations.

I ran the network configurations and experiments in my own Docker and Mininet environment, collected the results, and checked the explanations against my actual evidence.

### Week 6 Webpage

https://christineleow04.github.io/wic2005-netlab/week6/
