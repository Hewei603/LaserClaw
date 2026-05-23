# ReZonator 仿真记录示例
# [SAMPLE DATA — 示例数据，非真实实验室文件]

## 实验案例：Nd:YAG 线形腔仿真

### 仿真目标
确定 Nd:YAG CW 激光器线形腔的稳定工作区间，优化腔长和输出镜曲率半径。

### 腔型参数

```
腔型：线形腔（Fabry-Perot）
总腔长：L = 150 mm

元件列表（从 HR 镜到 OC 镜）：
1. HR 镜（平面镜，R = ∞，HR @ 1064 nm）
2. 自由传播：d₁ = 30 mm
3. Nd:YAG 晶体（长度 = 50 mm，n = 1.82，布儒斯特角切割）
4. 自由传播：d₂ = 30 mm
5. OC 镜（凹面镜，R = 200 mm，T = 10% @ 1064 nm）
```

### ReZonator 输入文件（.rz 格式示意）

```
[Cavity]
type = linear
wavelength = 1064e-9

[Element_1]
type = mirror
R = inf
label = HR

[Element_2]
type = free_space
L = 0.030

[Element_3]
type = crystal
L = 0.050
n = 1.82
label = NdYAG

[Element_4]
type = free_space
L = 0.030

[Element_5]
type = mirror
R = 0.200
T = 0.10
label = OC
```

### 仿真结果

| 参数 | 数值 |
|------|------|
| 腔内束腰（晶体中心）| w₀ = 0.42 mm |
| OC 处光斑尺寸 | w_OC = 0.38 mm |
| HR 处光斑尺寸 | w_HR = 0.35 mm |
| 稳定性参数 g₁g₂ | 0.62（稳定区间 0–1）|
| 腔模体积 | ~0.028 cm³ |

### 稳定性分析

腔长扫描（100–200 mm）：
- 100 mm：g₁g₂ = 0.45，稳定
- 150 mm：g₁g₂ = 0.62，稳定（当前设计）
- 180 mm：g₁g₂ = 0.89，接近不稳定边界
- 200 mm：g₁g₂ = 1.02，不稳定

**结论**：腔长应保持在 100–175 mm 范围内以确保稳定工作。

### 热透镜补偿

泵浦功率 3W 时，Nd:YAG 热透镜焦距估算：
- f_thermal ≈ 200 mm（经验公式）
- 等效腔长变化：Δg₁g₂ ≈ +0.15
- 补偿方案：将 OC 曲率半径从 200 mm 调整为 250 mm

### 下一步仿真计划
1. 扫描 OC 曲率半径（150–300 mm）
2. 加入热透镜模型，分析功率相关稳定性
3. 计算不同腔长下的模式匹配效率
