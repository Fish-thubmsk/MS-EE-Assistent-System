---
subject: 数学
chapter: 高等数学-极限与连续
type: note
date: 2024-01-10
---

# 极限与连续

## 极限的定义

设函数 $f(x)$ 在点 $x_0$ 的某去心邻域内有定义，若存在常数 $L$，使得对任意 $\varepsilon > 0$，存在 $\delta > 0$，当 $0 < |x - x_0| < \delta$ 时，有 $|f(x) - L| < \varepsilon$，则称 $L$ 为函数 $f(x)$ 当 $x \to x_0$ 时的极限，记作 $\lim_{x \to x_0} f(x) = L$。

## 重要极限

1. $\lim_{x \to 0} \frac{\sin x}{x} = 1$
2. $\lim_{x \to \infty} \left(1 + \frac{1}{x}\right)^x = e$

## 连续性

若 $\lim_{x \to x_0} f(x) = f(x_0)$，则称 $f(x)$ 在 $x_0$ 处连续。

## 易错点

- 混淆极限存在与函数在该点有定义：极限存在不意味着函数在该点有定义。
- 计算 $\lim_{x \to 0} x \sin\frac{1}{x}$ 时，注意 $\sin\frac{1}{x}$ 有界，所以极限为 0。
