import { MathfieldElement } from "./vendor/mathlive.min.mjs";

const STRINGS = {
  en: {
    acceptInsert: "Insert",
    acceptUpdate: "Update",
    cancel: "Cancel",
    ready: "Ready",
    latexRequired: "Enter a LaTeX formula first.",
    rows: "Rows",
    columns: "Columns",
    tabs: {
      greek: "Greek",
      structures: "Structures",
      delimiters: "Delimiters",
      analysis: "Analysis",
      algebra: "Algebra",
      geometry: "Geometry",
      topology: "Topology",
      relations: "Relations",
      operators: "Operators",
      bigops: "Big Ops",
      arrows: "Arrows",
      sets: "Sets",
      functions: "Functions",
      probability: "Probability",
      chemistry: "Chemistry",
      physics: "Physics",
      accents: "Accents",
      misc: "Misc",
    },
  },
  zh: {
    acceptInsert: "插入",
    acceptUpdate: "更新",
    cancel: "取消",
    ready: "就绪",
    latexRequired: "请先输入 LaTeX 公式。",
    rows: "行数",
    columns: "列数",
    tabs: {
      greek: "希腊",
      structures: "结构",
      delimiters: "分隔符",
      analysis: "分析",
      algebra: "代数",
      geometry: "几何",
      topology: "拓扑",
      relations: "关系",
      operators: "运算",
      bigops: "大型",
      arrows: "箭头",
      sets: "集合",
      functions: "函数",
      probability: "概率",
      chemistry: "化学",
      physics: "物理",
      accents: "字体",
      misc: "其他",
    },
  },
};

const GROUPS = [
  {
    id: "greek",
    items: [
      ["α", "\\alpha"], ["β", "\\beta"], ["γ", "\\gamma"], ["δ", "\\delta"], ["π", "\\pi"],
      ["σ", "\\sigma"], ["θ", "\\theta"], ["λ", "\\lambda"], ["μ", "\\mu"], ["ω", "\\omega"],
      ["φ", "\\phi"], ["τ", "\\tau"], ["ε", "\\epsilon"], ["κ", "\\kappa"], ["ρ", "\\rho"],
      ["ζ", "\\zeta"], ["η", "\\eta"], ["ι", "\\iota"], ["ν", "\\nu"], ["ξ", "\\xi"],
      ["υ", "\\upsilon"], ["χ", "\\chi"], ["ψ", "\\psi"],
      ["Γ", "\\Gamma"], ["Δ", "\\Delta"], ["Θ", "\\Theta"], ["Λ", "\\Lambda"], ["Π", "\\Pi"],
      ["Σ", "\\Sigma"], ["Φ", "\\Phi"], ["Ψ", "\\Psi"], ["Ω", "\\Omega"], ["Ξ", "\\Xi"],
      ["ϑ", "\\vartheta"], ["ϕ", "\\varphi"], ["ϵ", "\\varepsilon"], ["ϰ", "\\varkappa"],
      ["ϖ", "\\varpi"], ["ϱ", "\\varrho"], ["ς", "\\varsigma"], ["ϝ", "\\digamma"],
      ["∂", "\\partial"], ["∇", "\\nabla"], ["∞", "\\infty"],
      ["ℵ", "\\aleph"], ["ℶ", "\\beth"], ["ℷ", "\\gimel"], ["ℸ", "\\daleth"],
    ],
  },
  {
    id: "structures",
    structures: true,
    items: [
      ["分数", "\\frac{#?}{#?}", "Fraction"],
      ["上标", "^{#?}", "Superscript"],
      ["下标", "_{#?}", "Subscript"],
      ["上下标", "_{#?}^{#?}", "Subscript and superscript"],
      ["根号", "\\sqrt{#?}", "Square root"],
      ["n 次根", "\\sqrt[#?]{#?}", "Nth root"],
      ["求和", "\\sum_{#?}^{#?} #?", "Summation"],
      ["积分", "\\int_{#?}^{#?} #?\\,d#?", "Integral"],
      ["极限", "\\lim_{#? \\to #?} #?", "Limit"],
      ["乘积", "\\prod_{#?}^{#?} #?", "Product"],
      ["二项式", "\\binom{#?}{#?}", "Binomial"],
      ["对齐", "\\begin{aligned} #? &= #? \\\\ #? &= #? \\end{aligned}", "Aligned equations"],
      ["分段", "matrix:cases", "Cases"],
      ["矩阵", "matrix:matrix", "Matrix"],
      ["方括号矩阵", "matrix:bmatrix", "Bracketed matrix"],
      ["海森矩阵", "matrix:hessian", "Hessian matrix"],
      ["行列式", "matrix:vmatrix", "Determinant"],
      ["圆括号矩阵", "matrix:pmatrix", "Parenthesized matrix"],
      ["花括号矩阵", "matrix:Bmatrix", "Braced matrix"],
    ],
  },
  {
    id: "delimiters",
    items: [
      ["( )", "\\left( #? \\right)", "Parentheses"],
      ["[ ]", "\\left[ #? \\right]", "Brackets"],
      ["{ }", "\\left\\{ #? \\right\\}", "Braces"],
      ["| |", "\\left| #? \\right|", "Absolute value"],
      ["‖ ‖", "\\left\\| #? \\right\\|", "Norm"],
      ["⟨ ⟩", "\\left\\langle #? \\right\\rangle", "Angle brackets"],
      ["⎡ ⎤", "\\left\\lceil #? \\right\\rceil", "Ceiling"],
      ["⎣ ⎦", "\\left\\lfloor #? \\right\\rfloor", "Floor"],
      ["⟦ ⟧", "\\left\\llbracket #? \\right\\rrbracket", "Double brackets"],
      ["⌜ ⌝", "\\left\\ulcorner #? \\right\\urcorner", "Top corners"],
      ["⌞ ⌟", "\\left\\llcorner #? \\right\\lrcorner", "Bottom corners"],
      ["/", "/", "Slash"],
      ["\\", "\\backslash", "Backslash"],
      ["( ]", "\\left( #? \\right]", "Half-open left"],
      ["[ )", "\\left[ #? \\right)", "Half-open right"],
      ["⎛ ⎞", "\\left\\lgroup #? \\right\\rgroup", "Grouping parentheses"],
      ["\\bigl( \\bigr)", "\\bigl(#?\\bigr)", "Big parentheses"],
      ["\\bigl[ \\bigr]", "\\bigl[#?\\bigr]", "Big brackets"],
      ["\\bigl\\{ \\bigr\\}", "\\bigl\\{#?\\bigr\\}", "Big braces"],
      ["\\bigl\\langle \\bigr\\rangle", "\\bigl\\langle#?\\bigr\\rangle", "Big angle brackets"],
      ["\\bigl\\lvert \\bigr\\rvert", "\\bigl\\lvert#?\\bigr\\rvert", "Big absolute"],
      ["\\bigl\\lVert \\bigr\\rVert", "\\bigl\\lVert#?\\bigr\\rVert", "Big norm"],
      ["\\left. \\right|", "\\left. #? \\right|_{#?}", "Evaluation at"],
      ["\\underbrace{}_{}", "\\underbrace{#?}_{#?}", "Underbrace"],
      ["\\overbrace{}^{}", "\\overbrace{#?}^{#?}", "Overbrace"],
      ["\\boxed{}", "\\boxed{#?}", "Boxed"],
      ["\\cancel{}", "\\cancel{#?}", "Cancel"],
      ["\\sout{}", "\\sout{#?}", "Strikethrough"],
      ["\\overset{}{}", "\\overset{#?}{#?}", "Overset"],
      ["\\underset{}{}", "\\underset{#?}{#?}", "Underset"],
      ["\\underline{}", "\\underline{#?}", "Underline"],
      ["\\overline{}", "\\overline{#?}", "Overline"],
      ["\\overrightarrow{}", "\\overrightarrow{#?}", "overrightarrow"],
      ["\\overleftarrow{}", "\\overleftarrow{#?}", "overleftarrow"],
    ],
  },
  {
    id: "analysis",
    structures: true,
    items: [
      ["导数", "\\frac{d}{dx}", "Derivative"],
      ["偏导", "\\frac{\\partial #?}{\\partial #?}", "Partial derivative"],
      ["微分", "#?\\,d#?", "Differential"],
      ["不定积分", "\\int #?\\,d#?", "Indefinite integral"],
      ["定积分", "\\int_{#?}^{#?} #?\\,d#?", "Definite integral"],
      ["极限", "\\lim_{#? \\to #?} #?", "Limit"],
      ["梯度", "\\nabla #?", "Gradient"],
      ["散度", "\\nabla\\cdot #?", "Divergence"],
      ["旋度", "\\nabla\\times #?", "Curl"],
      ["拉普拉斯", "\\nabla^2 #?", "Laplacian"],
      ["级数", "\\sum_{n=0}^{\\infty} #?", "Series"],
      ["泰勒", "\\sum_{n=0}^{\\infty} \\frac{#?^{(n)}(#?)}{n!}(x-#?)^n", "Taylor expansion"],
      ["方向导数", "\\nabla_{\\mathbf{v}} f", "Directional derivative"],
      ["雅可比", "\\frac{\\partial(#?,\\ldots)}{\\partial(#?,\\ldots)}", "Jacobian"],
      ["链式法则", "\\frac{d}{dt}f(\\mathbf{r}(t)) = \\nabla f\\cdot\\mathbf{r}'(t)", "Chain rule"],
      ["全微分", "df = \\frac{\\partial f}{\\partial x}dx + \\frac{\\partial f}{\\partial y}dy", "Total differential"],
      ["隐函数", "\\frac{dy}{dx} = -\\frac{\\partial F/\\partial x}{\\partial F/\\partial y}", "Implicit function"],
      ["拉格朗日乘数", "\\mathcal{L}(x,\\lambda) = f(x) - \\lambda g(x)", "Lagrange multiplier"],
      ["欧拉-拉格朗日", "\\frac{\\partial\\mathcal{L}}{\\partial q} - \\frac{d}{dt}\\frac{\\partial\\mathcal{L}}{\\partial\\dot{q}} = 0", "Euler-Lagrange"],
      ["拉普拉斯变换", "\\mathcal{L}\\{f\\}(s) = \\int_0^\\infty f(t)e^{-st}dt", "Laplace transform"],
      ["傅里叶变换", "\\hat{f}(\\xi) = \\int_{-\\infty}^{\\infty} f(x)e^{-2\\pi i x\\xi}dx", "Fourier transform"],
      ["傅里叶级数", "f(x) = \\sum_{n=-\\infty}^{\\infty} c_n e^{inx}", "Fourier series"],
      ["卷积", "(f * g)(x) = \\int_{-\\infty}^{\\infty} f(y)g(x-y)dy", "Convolution"],
      ["逆傅里叶", "f(x) = \\int_{-\\infty}^{\\infty} \\hat{f}(\\xi)e^{2\\pi i x\\xi}d\\xi", "Inverse Fourier transform"],
      ["高阶导", "\\frac{d^{#?}}{dx^{#?}}", "Higher derivative"],
      ["混合偏导", "\\frac{\\partial^2 #?}{\\partial #?\\,\\partial #?}", "Mixed partial"],
      ["物质导数", "\\frac{D}{Dt} = \\frac{\\partial}{\\partial t} + \\mathbf{v}\\cdot\\nabla", "Material derivative"],
      ["变分", "\\delta #?", "Variation"],
      ["上极限", "\\limsup_{#? \\to #?} #?", "Limit superior"],
      ["下极限", "\\liminf_{#? \\to #?} #?", "Limit inferior"],
      ["幂级数", "\\sum_{n=0}^{\\infty} a_n (x - c)^n", "Power series"],
      ["麦克劳林", "\\sum_{n=0}^{\\infty} \\frac{#?^{(n)}(0)}{n!} x^n", "Maclaurin series"],
      ["曲线积分", "\\oint #?\\,d#?", "Contour integral"],
      ["二重积分", "\\iint_{#?} #?\\,d#?", "Double integral"],
      ["曲面积分", "\\oiint_{#?} #?\\,dS", "Surface integral"],
      ["体积分", "\\iiint_{#?} #?\\,dV", "Volume integral"],
      ["双调和", "\\nabla^4 #?", "Biharmonic"],
      ["狄拉克 delta", "\\delta(x)", "Dirac delta"],
      ["单位阶跃", "H(x) = \\begin{cases}0 & x<0\\\\ 1 & x\\ge 0\\end{cases}", "Heaviside step"],
      ["符号函数", "\\operatorname{sgn}(x) = \\begin{cases}-1 & x<0\\\\ 0 & x=0\\\\ 1 & x>0\\end{cases}", "Sign function"],
      ["误差函数", "\\operatorname{erf}(x) = \\frac{2}{\\sqrt{\\pi}}\\int_0^x e^{-t^2}dt", "Error function"],
      ["伽马函数", "\\Gamma(z) = \\int_0^\\infty t^{z-1}e^{-t}dt", "Gamma function"],
      ["黎曼 zeta", "\\zeta(s) = \\sum_{n=1}^\\infty \\frac{1}{n^s}", "Riemann zeta"],
      ["热方程", "\\frac{\\partial u}{\\partial t} = \\alpha\\nabla^2 u", "Heat equation"],
      ["波动方程", "\\frac{\\partial^2 u}{\\partial t^2} = c^2\\nabla^2 u", "Wave equation"],
      ["拉普拉斯方程", "\\nabla^2 u = 0", "Laplace equation"],
      ["泊松方程", "\\nabla^2 u = f", "Poisson equation"],
      ["亥姆霍兹", "\\nabla^2 u + k^2 u = 0", "Helmholtz equation"],
      ["纳维-斯托克斯", "\\frac{\\partial\\mathbf{u}}{\\partial t}+(\\mathbf{u}\\cdot\\nabla)\\mathbf{u}=-\\nabla p+\\nu\\nabla^2\\mathbf{u}", "Navier-Stokes"],
      ["傅里叶系数", "c_n = \\frac{1}{2\\pi}\\int_{-\\pi}^{\\pi} f(x)e^{-inx}dx", "Fourier coefficient"],
      ["帕塞瓦尔", "\\sum_{n=-\\infty}^{\\infty} |c_n|^2 = \\frac{1}{2\\pi}\\int_{-\\pi}^{\\pi} |f(x)|^2dx", "Parseval identity"],
      ["普朗歇尔", "\\int_{-\\infty}^{\\infty} |f(x)|^2dx = \\int_{-\\infty}^{\\infty} |\\hat{f}(\\xi)|^2d\\xi", "Plancherel theorem"],
      ["赫尔德不等式", "\\int_\\Omega |fg|dx \\le \\left(\\int_\\Omega |f|^p dx\\right)^{1/p}\\left(\\int_\\Omega |g|^q dx\\right)^{1/q}", "Holder inequality"],
      ["闵可夫斯基", "\\left(\\int |f+g|^p\\right)^{1/p} \\le \\left(\\int |f|^p\\right)^{1/p} + \\left(\\int |g|^p\\right)^{1/p}", "Minkowski inequality"],
      ["庞加莱不等式", "\\int_\\Omega |u-\\bar{u}|^2 dx \\le C\\int_\\Omega |\\nabla u|^2 dx", "Poincare inequality"],
      ["索伯列夫范数", "\\|u\\|_{W^{k,p}(\\Omega)} = \\left(\\sum_{|\\alpha|\\le k}\\int_\\Omega |D^\\alpha u|^p dx\\right)^{1/p}", "Sobolev norm"],
      ["离散傅里叶", "\\hat{f}[k] = \\sum_{n=0}^{N-1} f[n]e^{-2\\pi i kn/N}", "Discrete Fourier transform"],
      ["短时傅里叶", "S(\\tau,\\omega) = \\int f(t)g(t-\\tau)e^{-i\\omega t}dt", "Short-time Fourier transform"],
      ["小波变换", "W_f(a,b) = \\frac{1}{\\sqrt{a}}\\int f(t)\\overline{\\psi\\!\\left(\\frac{t-b}{a}\\right)}dt", "Wavelet transform"],
      ["勒让德多项式", "P_n(x) = \\frac{1}{2^n n!}\\frac{d^n}{dx^n}(x^2-1)^n", "Legendre polynomials"],
      ["连带勒让德", "P_l^m(x) = (-1)^m(1-x^2)^{m/2}\\frac{d^m}{dx^m}P_l(x)", "Associated Legendre"],
      ["球谐函数", "Y_l^m(\\theta,\\phi) = \\sqrt{\\frac{2l+1}{4\\pi}\\frac{(l-m)!}{(l+m)!}}P_l^m(\\cos\\theta)e^{im\\phi}", "Spherical harmonics"],
      ["贝塞尔函数 J", "J_n(x) = \\sum_{k=0}^\\infty \\frac{(-1)^k}{k!\\,\\Gamma(n+k+1)}\\left(\\frac{x}{2}\\right)^{2k+n}", "Bessel J"],
      ["埃尔米特多项式", "H_n(x) = (-1)^n e^{x^2}\\frac{d^n}{dx^n}e^{-x^2}", "Hermite polynomials"],
      ["拉盖尔多项式", "L_n(x) = \\frac{e^x}{n!}\\frac{d^n}{dx^n}(x^n e^{-x})", "Laguerre polynomials"],
      ["切比雪夫 T", "T_n(x) = \\cos(n\\arccos x)", "Chebyshev T"],
      ["贝塔函数", "\\mathrm{B}(p,q) = \\int_0^1 t^{p-1}(1-t)^{q-1}dt", "Beta function"],
      ["超几何 2F1", "{}_2F_1(a,b;c;z) = \\sum_{n=0}^\\infty\\frac{(a)_n(b)_n}{(c)_n}\\frac{z^n}{n!}", "Hypergeometric 2F1"],
      ["输运方程", "\\frac{\\partial u}{\\partial t} + \\mathbf{a}\\cdot\\nabla u = 0", "Transport equation"],
      ["对流扩散", "\\frac{\\partial u}{\\partial t} + \\mathbf{v}\\cdot\\nabla u = D\\nabla^2 u", "Advection-diffusion"],
      ["伯格方程", "\\frac{\\partial u}{\\partial t} + u\\frac{\\partial u}{\\partial x} = \\nu\\frac{\\partial^2 u}{\\partial x^2}", "Burgers equation"],
      ["KdV 方程", "\\frac{\\partial u}{\\partial t} + u\\frac{\\partial u}{\\partial x} + \\frac{\\partial^3 u}{\\partial x^3} = 0", "KdV equation"],
      ["欧拉方程", "\\frac{\\partial\\mathbf{u}}{\\partial t}+(\\mathbf{u}\\cdot\\nabla)\\mathbf{u} = -\\nabla p", "Euler equations"],
      ["程函方程", "|\\nabla u| = 1", "Eikonal equation"],
      ["反应扩散", "\\frac{\\partial u}{\\partial t} = D\\nabla^2 u + f(u)", "Reaction-diffusion"],
      ["希尔伯特变换", "\\mathcal{H}f(x) = \\frac{1}{\\pi}\\operatorname{p.v.}\\int_{-\\infty}^{\\infty}\\frac{f(y)}{x-y}dy", "Hilbert transform"],
      ["泊松求和", "\\sum_{n=-\\infty}^{\\infty} f(n) = \\sum_{k=-\\infty}^{\\infty} \\hat{f}(k)", "Poisson summation"],
      ["拉普拉斯逆", "f(t) = \\frac{1}{2\\pi i}\\int_{\\sigma-i\\infty}^{\\sigma+i\\infty}F(s)e^{st}ds", "Inverse Laplace"],
      ["梅林变换", "\\mathcal{M}\\{f\\}(s) = \\int_0^\\infty f(x)x^{s-1}dx", "Mellin transform"],
      ["拉克斯-米尔格拉姆", "a(u,v) = \\langle f, v \\rangle \\quad \\forall v \\in V", "Lax-Milgram"],
      ["里斯表示", "\\langle f, \\cdot \\rangle \\leftrightarrow f", "Riesz representation"],
      ["弗雷歇导数", "Df(x)[h] = \\lim_{t\\to 0}\\frac{f(x+th)-f(x)}{t}", "Frechet derivative"],
      ["黑-舒尔斯", "\\frac{\\partial V}{\\partial t}+\\frac12\\sigma^2 S^2\\frac{\\partial^2 V}{\\partial S^2}+rS\\frac{\\partial V}{\\partial S}-rV=0", "Black-Scholes"],
      ["索伯列夫嵌入", "W^{k,p}(\\Omega) \\hookrightarrow L^q(\\Omega)", "Sobolev embedding"],
      ["索伯列夫不等式", "\\|u\\|_{L^q(\\mathbb{R}^n)} \\le C\\|\\nabla u\\|_{L^p(\\mathbb{R}^n)}", "Sobolev inequality"],
      ["雅可比椭圆 sn", "\\operatorname{sn}(u,k)", "Jacobi elliptic sn"],
      ["δ 函数", "\\delta_{ij} = \\begin{cases}1 & i=j\\\\ 0 & i\\ne j\\end{cases}", "Kronecker delta"],
      ["缓增分布", "\\mathcal{S}'(\\mathbb{R}^n)", "Tempered distributions"],
      ["施瓦茨空间", "\\mathcal{S}(\\mathbb{R}^n) = \\left\\{\\varphi\\in C^\\infty: \\sup|x^\\alpha D^\\beta\\varphi|<\\infty\\right\\}", "Schwartz space"],
      ["格林函数", "G(x,x')", "Green's function"],
      ["Riesz 势", "I_\\alpha f(x) = \\int \\frac{f(y)}{|x-y|^{n-\\alpha}}dy", "Riesz potential"],
      ["Weierstrass 逼近", "|f(x)-B_nf(x)| \\to 0", "Weierstrass approx"],
      ["Fourier-Legendre", "f(x) = \\sum_{n=0}^\\infty a_n P_n(x)", "Fourier-Legendre series"],
      ["Carathéodory", "\\dot x = f(t,x),\\; f \\in L^1,\\; x \\in C^0", "Caratheodory"],
      ["Fenchel 对偶", "f^*(y) = \\sup_x\\langle x,y\\rangle - f(x)", "Fenchel dual"],
      ["震荡积分", "I(\\lambda) = \\int e^{i\\lambda\\varphi(x)}a(x)dx", "Oscillatory integral"],
      ["正弦变换", "\\hat{f}_s(\\xi) = \\int_0^{\\infty} f(x)\\sin(\\xi x)dx", "Sine transform"],
      ["余弦变换", "\\hat{f}_c(\\xi) = \\int_0^{\\infty} f(x)\\cos(\\xi x)dx", "Cosine transform"],
      ["汉克尔变换", "\\mathcal{H}_\\nu\\{f\\}(\\rho) = \\int_0^\\infty f(r)J_\\nu(\\rho r)rdr", "Hankel transform"],
      ["分数阶傅里叶", "\\mathcal{F}^\\alpha\\{f\\}(\\xi) = \\int_{-\\infty}^{\\infty} f(t)K_\\alpha(t,\\xi)dt", "Fractional Fourier"],
      ["拉东变换", "\\mathcal{R}f(\\theta,s) = \\int_{-\\infty}^{\\infty} f(s\\cos\\theta - t\\sin\\theta, s\\sin\\theta + t\\cos\\theta)dt", "Radon transform"],
      ["阿贝尔变换", "\\mathcal{A}\\{f\\}(y) = 2\\int_y^\\infty \\frac{f(r)r}{\\sqrt{r^2-y^2}}dr", "Abel transform"],
      ["Wigner-Ville", "W_x(t,\\omega) = \\int x(t+\\tau/2)\\overline{x(t-\\tau/2)}e^{-i\\omega\\tau}d\\tau", "Wigner-Ville"],
      ["模糊函数", "A_x(\\tau,\\nu) = \\int x(t+\\tau/2)\\overline{x(t-\\tau/2)}e^{2\\pi i\\nu t}dt", "Ambiguity function"],
      ["加博尔变换", "G_f(\\tau,\\omega) = \\int f(t)e^{-\\pi(t-\\tau)^2}e^{-i\\omega t}dt", "Gabor transform"],
      ["连续小波", "X_w(a,b) = \\frac{1}{\\sqrt{|a|}}\\int x(t)\\psi\\!\\left(\\frac{t-b}{a}\\right)dt", "CWT"],
      ["互相关", "(f \\star g)(\\tau) = \\int \\overline{f(t)}g(t+\\tau)dt", "Cross-correlation"],
      ["自相关", "R_f(\\tau) = \\int \\overline{f(t)}f(t+\\tau)dt", "Autocorrelation"],
      ["渐近展开", "#? \\sim \\sum_{n=0}^{\\infty} #? \\quad (#? \\to #?)", "Asymptotic expansion"],
      ["急减函数", "\\lim_{|x|\\to\\infty}|x|^k |D^\\alpha\\varphi(x)| = 0", "Rapidly decreasing"],
      ["艾里函数 Bi", "\\operatorname{Bi}(x) = \\frac{1}{\\pi}\\int_0^\\infty \\left[e^{-t^3/3}+\\sin\\!\\left(\\frac{t^3}{3}+xt\\right)\\right]dt", "Airy Bi"],
      ["切比雪夫 U", "U_n(x) = \\frac{\\sin((n+1)\\arccos x)}{\\sin(\\arccos x)}", "Chebyshev U"],
      ["盖根鲍尔", "C_n^{(\\lambda)}(x) = \\frac{(2\\lambda)_n}{n!}\\,_2F_1\\!\\left(-n,2\\lambda+n;\\lambda+\\frac12;\\frac{1-x}{2}\\right)", "Gegenbauer"],
      ["雅可比多项式", "P_n^{(\\alpha,\\beta)}(x) = \\frac{(\\alpha+1)_n}{n!}\\,_2F_1\\!\\left(-n,1+\\alpha+\\beta+n;\\alpha+1;\\frac{1-x}{2}\\right)", "Jacobi polynomials"],
      ["合流超几何 1F1", "{}_1F_1(a;b;z) = \\sum_{n=0}^\\infty\\frac{(a)_n}{(b)_n}\\frac{z^n}{n!}", "Confluent 1F1"],
      ["雅可比椭圆 cn", "\\operatorname{cn}(u,k)", "Jacobi elliptic cn"],
      ["雅可比椭圆 dn", "\\operatorname{dn}(u,k)", "Jacobi elliptic dn"],
      ["魏尔斯特拉斯 P", "\\wp(z;g_2,g_3) = \\frac{1}{z^2}+\\sum_{\\omega\\in\\Lambda\\setminus\\{0\\}}\\!\\left(\\frac{1}{(z-\\omega)^2}-\\frac{1}{\\omega^2}\\right)", "Weierstrass P"],
      ["分部积分", "\\int u\\,dv = uv - \\int v\\,du", "Integration by parts"],
      ["牛顿-莱布尼茨", "\\int_a^b f'(x)dx = f(b)-f(a)", "Newton-Leibniz"],
      ["格林定理", "\\oint_C (L\\,dx+M\\,dy) = \\iint_D \\left(\\frac{\\partial M}{\\partial x}-\\frac{\\partial L}{\\partial y}\\right)dA", "Green theorem"],
      ["散度定理", "\\iiint_V \\nabla\\cdot\\mathbf{F}\\,dV = \\oiint_S \\mathbf{F}\\cdot d\\mathbf{S}", "Divergence theorem"],
      ["斯托克斯定理", "\\int_{\\partial M} \\omega = \\int_M d\\omega", "Stokes theorem"],
      ["柯西积分公式", "f(a) = \\frac{1}{2\\pi i}\\oint_\\gamma \\frac{f(z)}{z-a}dz", "Cauchy integral formula"],
      ["留数定理", "\\oint_\\gamma f(z)dz = 2\\pi i\\sum\\operatorname{Res}(f,a_k)", "Residue theorem"],
      ["欧拉公式", "e^{i\\theta} = \\cos\\theta + i\\sin\\theta", "Euler formula"],
      ["牛顿迭代", "x_{n+1} = x_n - \\frac{f(x_n)}{f'(x_n)}", "Newton method"],
      ["中值定理", "f(b)-f(a) = f'(\\xi)(b-a)", "Mean value theorem"],
      ["L'Hôpital", "\\lim_{x\\to a}\\frac{f(x)}{g(x)} = \\lim_{x\\to a}\\frac{f'(x)}{g'(x)}", "L'Hopital rule"],
      ["柯西-施瓦茨", "|\\langle x,y\\rangle| \\le \\|x\\|\\,\\|y\\|", "Cauchy-Schwarz"],
      ["三角不等式", "\\|x+y\\| \\le \\|x\\| + \\|y\\|", "Triangle inequality"],
      ["Stirling", "n! \\sim \\sqrt{2\\pi n}\\,\\left(\\frac{n}{e}\\right)^n", "Stirling formula"],
      ["Wallis 乘积", "\\frac{\\pi}{2} = \\prod_{n=1}^\\infty \\frac{4n^2}{4n^2-1}", "Wallis product"],
      ["Euler 常数", "\\gamma = \\lim_{n\\to\\infty}\\left(\\sum_{k=1}^n\\frac1k-\\ln n\\right)", "Euler constant"],
      ["调和级数", "H_n = \\sum_{k=1}^n \\frac{1}{k}", "Harmonic series"],
      ["比值判别法", "\\limsup\\left|\\frac{a_{n+1}}{a_n}\\right| < 1 \\implies \\sum a_n \\text{ conv}", "Ratio test"],
      ["卷积定理", "\\widehat{f*g}(\\xi) = \\hat{f}(\\xi)\\hat{g}(\\xi)", "Convolution theorem"],
      ["留数计算", "\\operatorname{Res}(f,a) = \\frac1{(k-1)!}\\lim_{z\\to a}\\frac{d^{k-1}}{dz^{k-1}}(z-a)^k f(z)", "Residue formula"],
      ["傅里叶逆离散", "f[n] = \\frac{1}{N}\\sum_{k=0}^{N-1} \\hat{f}[k]e^{2\\pi i kn/N}", "Inverse DFT"],
      ["Morse 引理", "f(x) = f(0) - x_1^2 - \\cdots - x_k^2 + x_{k+1}^2 + \\cdots + x_n^2", "Morse lemma"],
    ],
  },
  {
    id: "algebra",
    structures: true,
    items: [
      ["点乘", "#? \\cdot #?", "Dot product"],
      ["叉乘", "#? \\times #?", "Cross product"],
      ["内积", "\\left\\langle #?, #? \\right\\rangle", "Inner product"],
      ["范数", "\\left\\| #? \\right\\|", "Norm"],
      ["转置", "#?^{\\mathsf{T}}", "Transpose"],
      ["逆矩阵", "#?^{-1}", "Inverse"],
      ["迹", "\\operatorname{tr}(#?)", "Trace"],
      ["行列式", "\\det(#?)", "Determinant"],
      ["秩", "\\operatorname{rank}(#?)", "Rank"],
      ["特征值", "\\lambda", "Eigenvalue"],
      ["特征向量", "\\mathbf{v}", "Eigenvector"],
      ["单位阵", "I_{#?}", "Identity matrix"],
      ["对角阵", "\\operatorname{diag}(#?)", "Diagonal matrix"],
      ["向量列", "\\begin{bmatrix} #? \\\\ #? \\end{bmatrix}", "Column vector"],
      ["核", "\\ker(#?)", "Kernel"],
      ["像", "\\operatorname{im}(#?)", "Image"],
      ["余核", "\\operatorname{coker}(#?)", "Cokernel"],
      ["张成", "\\operatorname{span}\\{#?\\}", "Span"],
      ["正交投影", "\\mathbf{P} = \\mathbf{A}(\\mathbf{A}^{\\mathsf{T}}\\!\\mathbf{A})^{-1}\\mathbf{A}^{\\mathsf{T}}", "Projection"],
      ["最小二乘", "\\mathbf{A}^{\\mathsf{T}}\\!\\mathbf{A}\\mathbf{x} = \\mathbf{A}^{\\mathsf{T}}\\!\\mathbf{b}", "Least squares"],
      ["伪逆", "\\mathbf{A}^+", "Pseudoinverse"],
      ["群", "G", "Group"],
      ["阿贝尔群", "\\mathbb{Z}_n", "Abelian group"],
      ["环", "R", "Ring"],
      ["域", "\\mathbb{F}", "Field"],
      ["同态", "\\varphi: G \\to H", "Homomorphism"],
      ["同构", "G \\cong H", "Isomorphism"],
      ["自同构", "\\operatorname{Aut}(G)", "Automorphism"],
      ["理想", "I \\triangleleft R", "Ideal"],
      ["商群", "G / N", "Quotient group"],
      ["商环", "R / I", "Quotient ring"],
      ["置换群", "S_n", "Symmetric group"],
      ["循环群", "C_n", "Cyclic group"],
      ["二面体群", "D_{2n}", "Dihedral group"],
      ["群作用", "G \\times X \\to X", "Group action"],
      ["多项式环", "K[x_1,\\ldots,x_n]", "Polynomial ring"],
      ["局部化", "S^{-1}R", "Localization"],
      ["整环", "R \\text{ integral domain}", "Integral domain"],
      ["PID", "R \\text{ PID}", "Principal ideal domain"],
      ["UFD", "R \\text{ UFD}", "Unique factorization domain"],
      ["欧几里得环", "R \\text{ Euclidean}", "Euclidean domain"],
      ["有限域", "\\mathbb{F}_q", "Finite field"],
      ["代数闭包", "\\overline{K}", "Algebraic closure"],
      ["伽罗瓦群", "\\operatorname{Gal}(L/K)", "Galois group"],
      ["域扩张", "L/K", "Field extension"],
      ["正合列", "A \\xrightarrow{f} B \\xrightarrow{g} C", "Exact sequence"],
      ["短正合列", "0 \\to A \\xrightarrow{f} B \\xrightarrow{g} C \\to 0", "Short exact sequence"],
      ["蛇形引理", "\\ker f \\to \\ker g \\to \\ker h \\xrightarrow{\\delta} \\operatorname{coker}f \\to \\operatorname{coker}g \\to \\operatorname{coker}h", "Snake lemma"],
      ["张量积", "M \\otimes_R N", "Tensor product"],
      ["直和", "V \\oplus W", "Direct sum"],
      ["交换图", "\\begin{CD}A@>f>>B\\\\@VgVV@VVhV\\\\C@>k>>D\\end{CD}", "Commutative diagram"],
      ["李括号", "[X,Y]", "Lie bracket"],
      ["指数映射", "\\exp: \\mathfrak{g} \\to G", "Exponential map"],
      ["Killing 型", "B(X,Y) = \\operatorname{tr}(\\operatorname{ad}_X \\circ \\operatorname{ad}_Y)", "Killing form"],
      ["根系", "\\Phi \\subset \\mathfrak{h}^*", "Root system"],
      ["单李代数", "\\mathfrak{g}", "Simple Lie algebra"],
      ["最高权", "V(\\lambda)", "Highest weight module"],
      ["函子", "F: \\mathcal{C} \\to \\mathcal{D}", "Functor"],
      ["自然变换", "\\eta: F \\Rightarrow G", "Natural transformation"],
      ["伴随", "F \\dashv G", "Adjoint functor"],
      ["极限", "\\varprojlim F", "Limit"],
      ["余极限", "\\varinjlim F", "Colimit"],
      ["链复形", "\\cdots \\to C_{n+1} \\xrightarrow{\\partial} C_n \\xrightarrow{\\partial} C_{n-1} \\to \\cdots", "Chain complex"],
      ["同调", "H_n(C) = \\ker\\partial_n / \\operatorname{im}\\partial_{n+1}", "Homology"],
      ["上同调", "H^n(C) = \\ker d_n / \\operatorname{im} d_{n-1}", "Cohomology"],
      ["Tor", "\\operatorname{Tor}_n^R(A,B)", "Tor functor"],
      ["Ext", "\\operatorname{Ext}^n_R(A,B)", "Ext functor"],
      ["投射模", "P \\text{ projective}", "Projective module"],
      ["内射模", "I \\text{ injective}", "Injective module"],
      ["导出函子", "R^nF(A)", "Derived functor"],
      ["谱序列", "E^r_{p,q} \\Rightarrow E^\\infty_{p+q}", "Spectral sequence"],
      ["群上同调", "H^n(G,M)", "Group cohomology"],
      ["导出范畴", "D(\\mathcal{A})", "Derived category"],
      ["外代数", "\\bigwedge(V)", "Exterior algebra"],
      ["对称代数", "\\operatorname{Sym}(V)", "Symmetric algebra"],
      ["张量代数", "T(V)", "Tensor algebra"],
      ["Spec", "\\operatorname{Spec}(R)", "Prime spectrum"],
      ["Proj", "\\operatorname{Proj}(S)", "Projective spectrum"],
      ["概形", "(X,\\mathcal{O}_X)", "Scheme"],
      ["仿射簇", "V(f_1,\\ldots,f_k) \\subset \\mathbb{A}^n", "Affine variety"],
      ["射影簇", "V_+(F_1,\\ldots,F_k) \\subset \\mathbb{P}^n", "Projective variety"],
      ["C*-代数", "\\mathcal{A}", "C*-algebra"],
      ["李群", "G \\text{ Lie group}", "Lie group"],
      ["李代数", "\\mathfrak{g} = T_eG", "Lie algebra"],
      ["PBW 定理", "\\operatorname{gr} U(\\mathfrak{g}) \\cong \\operatorname{Sym}(\\mathfrak{g})", "PBW theorem"],
      ["Kronecker 积", "\\mathbf{A} \\otimes \\mathbf{B}", "Kronecker product"],
      ["矩阵指数", "e^{\\mathbf{A}} = \\sum_{n=0}^\\infty \\frac{\\mathbf{A}^n}{n!}", "Matrix exponential"],
      ["舒尔补", "\\mathbf{S} = \\mathbf{D} - \\mathbf{C}\\mathbf{A}^{-1}\\mathbf{B}", "Schur complement"],
      ["范德蒙", "V_{ij} = x_i^{j-1}", "Vandermonde matrix"],
      ["伴随表示", "\\operatorname{Ad}_g(X) = gXg^{-1}", "Adjoint representation"],
      ["线性方程组", "\\mathbf{A}\\mathbf{x} = \\mathbf{b}", "Linear system"],
      ["增广矩阵", "[\\mathbf{A}\\mid\\mathbf{b}]", "Augmented matrix"],
      ["Gram-Schmidt", "\\mathbf{u}_k = \\mathbf{v}_k - \\sum_{j<k}\\operatorname{proj}_{\\mathbf{u}_j}\\mathbf{v}_k", "Gram-Schmidt"],
      ["QR 分解", "\\mathbf{A} = \\mathbf{Q}\\mathbf{R}", "QR decomposition"],
      ["LU 分解", "\\mathbf{A} = \\mathbf{L}\\mathbf{U}", "LU decomposition"],
      ["SVD", "\\mathbf{A} = \\mathbf{U}\\boldsymbol{\\Sigma}\\mathbf{V}^{\\mathsf{T}}", "SVD"],
      ["谱分解", "\\mathbf{A} = \\mathbf{V}\\boldsymbol{\\Lambda}\\mathbf{V}^{-1}", "Spectral decomposition"],
      ["Cayley-Hamilton", "p(\\mathbf{A}) = 0", "Cayley-Hamilton"],
      ["伴随矩阵", "\\operatorname{adj}(\\mathbf{A})", "Adjugate matrix"],
      ["Jordan 标准形", "\\mathbf{J} = \\operatorname{diag}(J_1,\\ldots,J_k)", "Jordan form"],
      ["二次型", "Q(\\mathbf{x}) = \\mathbf{x}^{\\mathsf{T}}\\mathbf{A}\\mathbf{x}", "Quadratic form"],
      ["Hermite 矩阵", "\\mathbf{A}^{\\dagger} = \\mathbf{A}", "Hermitian matrix"],
      ["酉矩阵", "\\mathbf{U}^{\\dagger}\\mathbf{U} = \\mathbf{I}", "Unitary matrix"],
      ["对偶空间", "V^* = \\operatorname{Hom}(V,\\mathbb{F})", "Dual space"],
      ["Hilbert 空间", "\\mathcal{H}", "Hilbert space"],
      ["Banach 空间", "\\mathcal{B}", "Banach space"],
      ["自由群", "F_n", "Free group"],
      ["Noether 环", "R \\text{ Noetherian}", "Noetherian ring"],
      ["分式域", "\\operatorname{Frac}(R)", "Fraction field"],
      ["Jacobi 恒等式", "[X,[Y,Z]]+[Y,[Z,X]]+[Z,[X,Y]]=0", "Jacobi identity"],
      ["Dynkin 图", "A_n,B_n,C_n,D_n,E_6,E_7,E_8,F_4,G_2", "Dynkin diagram"],
      ["Weyl 群", "W", "Weyl group"],
      ["BCH 公式", "\\log(e^X e^Y) = X+Y+\\frac12[X,Y]+\\cdots", "Baker-Campbell-Hausdorff"],
      ["Schur 引理", "\\operatorname{Hom}_G(V,W) \\cong \\mathbb{C}", "Schur lemma"],
    ],
  },
  {
    id: "geometry",
    structures: true,
    items: [
      ["角度", "\\theta", "Angle"],
      ["度", "^\\circ", "Degree"],
      ["曲率", "\\kappa = \\frac{|\\mathbf{r}'\\times\\mathbf{r}''|}{|\\mathbf{r}'|^3}", "Curvature"],
      ["挠率", "\\tau = \\frac{(\\mathbf{r}'\\times\\mathbf{r}'')\\cdot\\mathbf{r}'''}{|\\mathbf{r}'\\times\\mathbf{r}''|^2}", "Torsion"],
      ["弧长", "s = \\int \\sqrt{g_{ij}dx^i dx^j}", "Arc length"],
      ["第一基本形式", "\\mathrm{I} = E\\,du^2 + 2F\\,du\\,dv + G\\,dv^2", "First fundamental form"],
      ["第二基本形式", "\\mathrm{II} = L\\,du^2 + 2M\\,du\\,dv + N\\,dv^2", "Second fundamental form"],
      ["高斯曲率", "K = \\frac{LN-M^2}{EG-F^2}", "Gaussian curvature"],
      ["平均曲率", "H = \\frac{EN+GL-2FM}{2(EG-F^2)}", "Mean curvature"],
      ["度量张量", "g = g_{ij}\\,dx^i\\otimes dx^j", "Metric tensor"],
      ["克里斯托费尔", "\\Gamma^k_{ij} = \\frac12 g^{kl}\\left(\\partial_i g_{jl}+\\partial_j g_{il}-\\partial_l g_{ij}\\right)", "Christoffel symbols"],
      ["协变导数", "\\nabla_i V^j = \\partial_i V^j + \\Gamma^j_{ik}V^k", "Covariant derivative"],
      ["李导数", "\\mathcal{L}_X Y = [X,Y]", "Lie derivative"],
      ["黎曼曲率", "R^i_{jkl} = \\partial_k\\Gamma^i_{jl}-\\partial_l\\Gamma^i_{jk}+\\Gamma^i_{mk}\\Gamma^m_{jl}-\\Gamma^i_{ml}\\Gamma^m_{jk}", "Riemann curvature"],
      ["里奇曲率", "R_{ij} = R^k_{ikj}", "Ricci curvature"],
      ["标量曲率", "R = g^{ij}R_{ij}", "Scalar curvature"],
      ["爱因斯坦张量", "G_{\\mu\\nu} = R_{\\mu\\nu} - \\frac12 R g_{\\mu\\nu}", "Einstein tensor"],
      ["测地线", "\\frac{d^2x^i}{dt^2}+\\Gamma^i_{jk}\\frac{dx^j}{dt}\\frac{dx^k}{dt}=0", "Geodesic"],
      ["平行移动", "V^i(t) = V^i(0) - \\int_0^t \\Gamma^i_{jk}\\dot{x}^j V^k dt", "Parallel transport"],
      ["联络", "\\nabla_X Y", "Connection"],
      ["切空间", "T_pM", "Tangent space"],
      ["余切空间", "T^*_pM", "Cotangent space"],
      ["微分形式", "\\Omega^k(M)", "Differential forms"],
      ["外微分", "d\\omega", "Exterior derivative"],
      ["楔积", "\\omega \\wedge \\eta", "Wedge product"],
      ["霍奇星", "\\star \\omega", "Hodge star"],
      ["霍奇拉普拉斯", "\\Delta = d\\!\\!\\!^\\dagger d + d d\\!\\!\\!^\\dagger", "Hodge Laplacian"],
      ["向量场", "X = X^i\\partial_i", "Vector field"],
      ["流", "\\phi_t: M \\to M", "Flow"],
      ["德拉姆上同调", "H^k_{\\mathrm{dR}}(M)", "de Rham cohomology"],
      ["霍奇定理", "H^k_{\\mathrm{dR}}(M) \\cong \\mathcal{H}^k(M)", "Hodge theorem"],
      ["霍奇分解", "\\Omega^k = \\operatorname{im}d \\oplus \\operatorname{im}d^\\dagger \\oplus \\mathcal{H}^k", "Hodge decomposition"],
      ["高斯-博内", "\\int_M K\\,dA = 2\\pi\\chi(M)", "Gauss-Bonnet theorem"],
      ["高斯-博内-陈", "\\int_M \\operatorname{Pf}(\\Omega) = (2\\pi)^n\\chi(M)", "Chern-Gauss-Bonnet"],
      ["陈类", "c_1(L) = \\left[\\frac{i}{2\\pi}F\\right]", "Chern class"],
      ["陈数", "\\int_M c_1(L) \\in \\mathbb{Z}", "Chern number"],
      ["陈特征", "\\operatorname{ch}(E) = \\operatorname{tr}\\exp\\!\\left(\\frac{i}{2\\pi}F\\right)", "Chern character"],
      ["托德类", "\\operatorname{Td}(TM)", "Todd class"],
      ["阿蒂亚-辛格", "\\operatorname{ind}(D) = \\int_M \\hat{A}(M)\\,\\operatorname{ch}(E)", "Atiyah-Singer index"],
      ["狄拉克算子", "\\displaystyle{\\not}D = \\gamma^\\mu\\nabla_\\mu", "Dirac operator"],
      ["旋量", "\\psi \\in \\Gamma(S)", "Spinor"],
      ["联络形式", "\\omega", "Connection form"],
      ["曲率形式", "\\Omega = d\\omega + \\omega\\wedge\\omega", "Curvature form"],
      ["规范场", "F = dA + A\\wedge A", "Gauge field"],
      ["杨-米尔斯", "D_\\mu F^{\\mu\\nu} = 0", "Yang-Mills equation"],
      ["陈-西蒙斯", "S_{\\mathrm{CS}} = \\int \\operatorname{tr}\\!\\left(A\\wedge dA + \\frac23 A\\wedge A\\wedge A\\right)", "Chern-Simons"],
      ["瞬子", "F = \\star F", "Instanton"],
      ["自对偶", "F^+ = 0", "Self-dual"],
      ["里奇流", "\\frac{\\partial g}{\\partial t} = -2\\operatorname{Ric}(g)", "Ricci flow"],
      ["爱因斯坦方程", "R_{\\mu\\nu} - \\frac12 R g_{\\mu\\nu} = 8\\pi T_{\\mu\\nu}", "Einstein field equations"],
      ["闵氏度量", "\\eta_{\\mu\\nu} = \\operatorname{diag}(-1,1,1,1)", "Minkowski metric"],
      ["凯勒流形", "(M, g, J, \\omega)", "Kahler manifold"],
      ["凯勒度量", "\\omega = i\\partial\\bar\\partial\\varphi", "Kahler metric"],
      ["卡拉比-丘", "c_1(M) = 0", "Calabi-Yau manifold"],
      ["Â-类", "\\hat{A}(M) = \\prod_{i=1}^n \\frac{x_i/2}{\\sinh(x_i/2)}", "A-hat genus"],
      ["L-类", "L(M) = \\prod_{i=1}^n \\frac{x_i}{\\tanh x_i}", "L-genus"],
      ["拉普拉斯-贝特拉米", "\\Delta = -\\star d\\!\\!\\!^\\dagger d \\star", "Laplace-Beltrami"],
      ["消灭定理", "H^0(M, K_M) = 0", "Vanishing theorem"],
      ["小平消灭", "H^q(M, \\Omega^p(K_M)) = 0 \\quad p+q>n", "Kodaira vanishing"],
      ["辛流形", "(M, \\omega)", "Symplectic manifold"],
      ["泊松括号", "\\{f,g\\} = \\omega(X_f,X_g)", "Poisson bracket"],
      ["矩映射", "\\mu: M \\to \\mathfrak{g}^*", "Moment map"],
      ["体积形式", "dV = \\sqrt{|g|}\\,dx^1\\wedge\\cdots\\wedge dx^n", "Volume form"],
      ["复流形", "(M,J)", "Complex manifold"],
      ["射影空间", "\\mathbb{CP}^n", "Complex projective space"],
      ["格拉斯曼流形", "\\operatorname{Gr}(k,n)", "Grassmannian"],
      ["Bianchi 恒等式", "\\nabla R(X,Y)Z + \\nabla R(Y,Z)X + \\nabla R(Z,X)Y = 0", "Bianchi identity"],
      ["截面曲率", "\\operatorname{Sect}(X,Y) = \\frac{\\langle R(X,Y)Y,X\\rangle}{|X\\wedge Y|^2}", "Sectional curvature"],
      ["Weyl 张量", "W = R - \\frac{1}{n-2}\\left(\\operatorname{Ric}-\\frac{R}{2(n-1)}g\\right)\\circ g", "Weyl tensor"],
      ["共形变换", "\\tilde{g} = e^{2f}g", "Conformal transformation"],
      ["复结构", "J: T_pM \\to T_pM,\\; J^2 = -I", "Complex structure"],
      ["Nijenhuis 张量", "N_J(X,Y) = [X,Y] + J[JX,Y] + J[X,JY] - [JX,JY]", "Nijenhuis tensor"],
      ["Kähler 形式", "\\omega = -\\operatorname{Im} g = g(J\\cdot,\\cdot)", "Kahler form"],
      ["Calabi-Yau", "\\operatorname{Ric}(\\omega) = 0", "Calabi-Yau condition"],
      ["全纯映射", "f: M \\to N,\\; df\\circ J_M = J_N\\circ df", "Holomorphic map"],
      ["特殊 holonomy", "\\operatorname{Hol}(g) \\subseteq G_2,\\; \\operatorname{Spin}(7)", "Special holonomy"],
      ["齐性空间", "G/H", "Homogeneous space"],
      ["对称空间", "\\nabla R = 0,\\; M = G/K", "Symmetric space"],
      ["接触形式", "\\alpha \\wedge (d\\alpha)^n \\neq 0", "Contact form"],
      ["辛约化", "\\mu^{-1}(0)/G", "Symplectic reduction"],
      ["Donaldson 不变量", "\\operatorname{SW}(M^4)", "Donaldson invariant"],
      ["Kuranishi 结构", "\\mathcal{K}", "Kuranishi structure"],
    ],
  },
  {
    id: "topology",
    structures: true,
    items: [
      ["开集", "U \\subset X", "Open set"],
      ["闭集", "F \\subset X", "Closed set"],
      ["紧致", "K \\subset X", "Compact"],
      ["连通", "X \\text{ connected}", "Connected"],
      ["道路连通", "\\pi_0(X) = 0", "Path-connected"],
      ["内部", "\\operatorname{int}(A)", "Interior"],
      ["闭包", "\\overline{A}", "Closure"],
      ["边界", "\\partial A", "Boundary"],
      ["邻域", "U \\ni x", "Neighborhood"],
      ["聚点", "x'", "Limit point"],
      ["度量空间", "(X,d)", "Metric space"],
      ["拓扑空间", "(X,\\mathcal{T})", "Topological space"],
      ["连续映射", "f: X \\to Y", "Continuous map"],
      ["同胚", "X \\cong Y", "Homeomorphism"],
      ["同伦", "f \\simeq g", "Homotopy"],
      ["基本群", "\\pi_1(X,x_0)", "Fundamental group"],
      ["高阶同伦", "\\pi_n(X)", "Higher homotopy group"],
      ["同调", "H_n(X;\\mathbb{Z})", "Homology"],
      ["上同调", "H^n(X;\\mathbb{Z})", "Cohomology"],
      ["贝蒂数", "b_n = \\operatorname{rank} H_n(X)", "Betti numbers"],
      ["欧拉示性数", "\\chi(X) = \\sum_{n}(-1)^n b_n", "Euler characteristic"],
      ["CW 复形", "X = \\bigcup_{n} X^{(n)}", "CW complex"],
      ["单纯形", "\\Delta^n", "Simplex"],
      ["复形", "K", "Simplicial complex"],
      ["胞腔同调", "H_n(X) \\cong H_n^{\\mathrm{CW}}(X)", "Cellular homology"],
      ["流形", "M^n", "Manifold"],
      ["带边流形", "\\partial M", "Manifold with boundary"],
      ["豪斯多夫", "T_2", "Hausdorff"],
      ["第二可数", "\\text{second countable}", "Second countable"],
      ["映射度", "\\deg(f) = \\sum_{x\\in f^{-1}(y)} \\operatorname{sgn} \\det df_x", "Mapping degree"],
      ["不动点", "\\operatorname{Fix}(f) = \\{x: f(x)=x\\}", "Fixed point"],
      ["莱夫谢茨", "L(f) = \\sum_k (-1)^k \\operatorname{tr}(f_*: H_k \\to H_k)", "Lefschetz number"],
      ["覆叠空间", "p: \\tilde{X} \\to X", "Covering space"],
      ["万有覆叠", "\\tilde{X}", "Universal cover"],
      ["纤维丛", "F \\to E \\xrightarrow{\\pi} B", "Fiber bundle"],
      ["向量丛", "E \\to M", "Vector bundle"],
      ["切丛", "TM", "Tangent bundle"],
      ["余切丛", "T^*M", "Cotangent bundle"],
      ["法丛", "\\nu = TM / T\\partial M", "Normal bundle"],
      ["球丛", "S(E) \\to M", "Sphere bundle"],
      ["悬垂", "\\Sigma X", "Suspension"],
      ["楔和", "X \\vee Y", "Wedge sum"],
      [" smash ", "X \\wedge Y", "Smash product"],
      ["无交并", "X \\sqcup Y", "Disjoint union"],
      ["拓扑和", "X \\cup_f Y", "Attaching space"],
      ["映射锥", "C_f = Y \\cup_f CX", "Mapping cone"],
      ["环路空间", "\\Omega X", "Loop space"],
      ["同伦纤维", "\\operatorname{hofib}(f)", "Homotopy fiber"],
      ["范坎彭", "\\pi_1(X) \\cong \\pi_1(U) *_{\\pi_1(U\\cap V)} \\pi_1(V)", "van Kampen theorem"],
      ["切除", "H_n(X,A) \\cong H_n(X\\setminus Z, A\\setminus Z)", "Excision theorem"],
      ["迈耶-维托里斯", "\\cdots\\!\\to\\!H_n(A\\cap B)\\!\\to\\!H_n(A)\\oplus H_n(B)\\!\\to\\!H_n(X)\\!\\to\\!H_{n-1}(A\\cap B)\\!\\to\\!\\cdots", "Mayer-Vietoris"],
      ["万有系数", "0 \\to H_n(X)\\otimes G \\to H_n(X;G) \\to \\operatorname{Tor}(H_{n-1}(X),G) \\to 0", "Universal coefficient"],
      ["Kunneth", "H_n(X\\times Y) \\cong \\bigoplus_{i+j=n} H_i(X)\\otimes H_j(Y)", "Kunneth formula"],
      ["庞加莱对偶", "H^k(M) \\cong H_{n-k}(M)", "Poincare duality"],
      ["杯积", "H^k \\times H^l \\xrightarrow{\\smile} H^{k+l}", "Cup product"],
      ["上同调环", "H^*(M)", "Cohomology ring"],
      ["示性类", "c(E) \\in H^*(B)", "Characteristic class"],
      ["陈类", "c_i(E) \\in H^{2i}(B;\\mathbb{Z})", "Chern class"],
      ["庞蒂亚金类", "p_i(E) \\in H^{4i}(B;\\mathbb{Z})", "Pontryagin class"],
      ["欧拉类", "e(E) \\in H^n(B;\\mathbb{Z})", "Euler class"],
      ["施蒂费尔-惠特尼", "w_i(E) \\in H^i(B;\\mathbb{Z}_2)", "Stiefel-Whitney class"],
      ["莫尔斯函数", "f: M \\to \\mathbb{R}", "Morse function"],
      ["临界点", "\\nabla f(p) = 0", "Critical point"],
      ["莫尔斯不等式", "M_k \\ge b_k", "Morse inequality"],
      ["莫尔斯同调", "HM_k(M,f)", "Morse homology"],
      ["塞尔谱序列", "E^2_{p,q} = H_p(B; H_q(F)) \\Rightarrow H_{p+q}(E)", "Serre spectral sequence"],
      ["托姆同构", "H^k(B) \\cong H^{k+n}(E,E_0)", "Thom isomorphism"],
      ["吉辛序列", "\\cdots \\to H^k(B) \\to H^k(S(E)) \\to H^{k-n+1}(B) \\to \\cdots", "Gysin sequence"],
      ["分类空间", "BG", "Classifying space"],
      ["普遍丛", "EG \\to BG", "Universal bundle"],
      ["配边", "\\Omega_n^O", "Cobordism"],
      ["拓扑量子场论", "Z: \\operatorname{Cob}_d \\to \\operatorname{Vect}", "TQFT"],
      ["上同调运算", "\\mathcal{O}: H^n(X;\\mathbb{Z}_p) \\to H^{n+k}(X;\\mathbb{Z}_p)", "Cohomology operation"],
      ["Steenrod 平方", "\\operatorname{Sq}^k: H^n \\to H^{n+k}", "Steenrod square"],
      ["代数K理论", "K_0(R),\\; K_1(R)", "Algebraic K-theory"],
      ["拓扑K理论", "K(X)", "Topological K-theory"],
      ["Bott 周期性", "K(X) \\cong K(\\Sigma^2 X)", "Bott periodicity"],
      ["Whitehead", "\\pi_k(X^{(n)}) \\cong \\pi_k(X),\\; k<n", "Whitehead theorem"],
      ["Hurewicz", "h: \\pi_n(X) \\to H_n(X)", "Hurewicz map"],
      ["微分同胚", "f: M \\to N", "Diffeomorphism"],
      ["Rohlin", "\\sigma(M^4) \\equiv 0 \\pmod{16}", "Rohlin theorem"],
      ["光滑结构", "M \\text{ smooth}", "Smooth structure"],
      ["奇异同调", "H_n^{\\operatorname{sing}}(X)", "Singular homology"],
      ["相对同调", "H_n(X,A)", "Relative homology"],
      ["Čech 上同调", "\\check{H}^n(\\mathcal{U}, \\mathcal{F})", "Cech cohomology"],
      ["层", "\\mathcal{F}", "Sheaf"],
      ["层上同调", "H^n(X,\\mathcal{F})", "Sheaf cohomology"],
      ["基本群 S¹", "\\pi_1(S^1) \\cong \\mathbb{Z}", "pi1 of circle"],
      ["Hopf 纤维化", "S^3 \\to S^2,\\; S^1 \\hookrightarrow S^3", "Hopf fibration"],
      ["映射类群", "\\operatorname{Mod}(S_g)", "Mapping class group"],
      ["Teichmüller", "\\mathcal{T}(S_g)", "Teichmuller space"],
      ["模空间", "\\mathcal{M}_g", "Moduli space"],
      ["Spin 结构", "\\operatorname{Spin}(n) \\to \\operatorname{SO}(n)", "Spin structure"],
      ["几乎复结构", "J \\in \\operatorname{End}(TM),\\; J^2 = -I", "Almost complex"],
      ["拓扑熵", "h_{\\mathrm{top}}(f)", "Topological entropy"],
      ["Heegaard 分解", "M = H_g \\cup_{\\phi} H_g", "Heegaard splitting"],
      ["Floer 同调", "\\operatorname{HF}(Y,\\mathfrak{s})", "Floer homology"],
      ["Khovanov 同调", "\\operatorname{Kh}(L)", "Khovanov homology"],
      ["L² 同调", "H_{(2)}^*(\\tilde{M})", "L2 homology"],
      ["Baum-Connes", "K_*(C_r^*(G)) \\cong K_*(BG)", "Baum-Connes"],
      ["Gromov 双曲", "\\delta\\text{-hyperbolic}", "Gromov hyperbolic"],
      ["Novikov 猜想", "\\operatorname{Sign}\\cong L(\\tilde{M})", "Novikov conjecture"],
    ],
  },
  {
    id: "relations",
    items: [
      ["=", "="], ["≠", "\\neq"], ["≈", "\\approx"], ["≡", "\\equiv"], ["∼", "\\sim"], ["≅", "\\cong"],
      ["≃", "\\simeq"], ["∝", "\\propto"], ["<", "<"], [">", ">"], ["≤", "\\leq"], ["≥", "\\geq"],
      ["≪", "\\ll"], ["≫", "\\gg"], ["≦", "\\leqq"], ["≧", "\\geqq"],
      ["≲", "\\lesssim"], ["≳", "\\gtrsim"], ["⪅", "\\lessapprox"], ["⪆", "\\gtrapprox"],
      ["≶", "\\lessgtr"], ["≷", "\\gtrless"], ["⋚", "\\lesseqgtr"], ["⋛", "\\gtreqless"],
      ["∈", "\\in"], ["∉", "\\notin"], ["∋", "\\ni"], ["⊂", "\\subset"], ["⊃", "\\supset"],
      ["⊆", "\\subseteq"], ["⊇", "\\supseteq"], ["⊊", "\\subsetneq"], ["⊋", "\\supsetneq"],
      ["⊄", "\\not\\subset"], ["⊅", "\\not\\supset"], ["⊈", "\\nsubseteq"], ["⊉", "\\nsupseteq"],
      ["⊏", "\\sqsubset"], ["⊐", "\\sqsupset"], ["⊑", "\\sqsubseteq"], ["⊒", "\\sqsupseteq"],
      ["≺", "\\prec"], ["≻", "\\succ"], ["≼", "\\preceq"], ["≽", "\\succeq"],
      ["⋞", "\\preccurlyeq"], ["⋟", "\\succcurlyeq"],
      ["∥", "\\parallel"], ["∦", "\\nparallel"], ["⊥", "\\perp"],
      ["∴", "\\therefore"], ["∵", "\\because"],
      ["≔", "\\coloneqq"], ["≕", "\\eqqcolon"], ["≜", "\\triangleq"],
      ["≑", "\\doteqdot"], ["≐", "\\doteq"], ["≗", "\\circeq"], ["≖", "\\eqcirc"],
      ["≘", "\\arceq"], ["≙", "\\widehat{=}"], ["≚", "\\veeeq"],
      ["≒", "\\fallingdotseq"], ["≓", "\\risingdotseq"], ["≊", "\\approxeq"],
      ["≉", "\\napprox"], ["≄", "\\nsimeq"], ["≇", "\\ncong"],
      ["∤", "\\nmid"], ["≁", "\\nsim"], ["⋠", "\\npreceq"], ["⋡", "\\nsucceq"],
      ["⊲", "\\vartriangleleft"], ["⊳", "\\vartriangleright"],
      ["⊴", "\\trianglelefteq"], ["⊵", "\\trianglerighteq"],
      ["⋈", "\\bowtie"], ["⋉", "\\ltimes"], ["⋊", "\\rtimes"],
      ["≬", "\\between"], ["≍", "\\asymp"], ["⋍", "\\backsimeq"],
      ["⊨", "\\models"], ["⊢", "\\vdash"], ["⊣", "\\dashv"],
      ["⊩", "\\Vdash"], ["⊪", "\\Vvdash"], ["⊧", "\\Dashv"],
      ["≛", "\\stargeq"],
      ["\\overset{!}{=}", "\\overset{!}{=}", "Must equal"],
      ["\\overset{\\text{def}}{=}", "\\overset{\\text{def}}{=}", "Defined as"],
      ["\\overset{?}{=}", "\\overset{?}{=}", "Questioned equality"],
    ],
  },
  {
    id: "operators",
    items: [
      ["+", "+"], ["−", "-"], ["±", "\\pm"], ["∓", "\\mp"], ["×", "\\times"], ["÷", "\\div"],
      ["·", "\\cdot"], ["∗", "\\ast"], ["∘", "\\circ"], ["∙", "\\bullet"],
      ["∩", "\\cap"], ["∪", "\\cup"], ["∧", "\\wedge"], ["∨", "\\vee"],
      ["⊕", "\\oplus"], ["⊖", "\\ominus"], ["⊗", "\\otimes"], ["⊘", "\\oslash"],
      ["⊙", "\\odot"], ["⊚", "\\circledcirc"], ["⊛", "\\circledast"],
      ["⊡", "\\boxdot"], ["⊞", "\\boxplus"], ["⊟", "\\boxminus"],
      ["⨁", "\\bigoplus"], ["⨂", "\\bigotimes"], ["⨀", "\\bigodot"],
      ["⋄", "\\diamond"], ["◊", "\\lozenge"], ["△", "\\triangle"],
      ["▷", "\\triangleright"], ["◁", "\\triangleleft"],
      ["∔", "\\dotplus"], ["⨿", "\\amalg"], ["⊎", "\\uplus"],
      ["⋓", "\\Cup"], ["⋒", "\\Cap"], ["∖", "\\setminus"],
      ["⊓", "\\sqcap"], ["⊔", "\\sqcup"], ["†", "\\dagger"], ["‡", "\\ddagger"],
      ["′", "^{\\prime}"], ["″", "^{\\prime\\prime}"], ["‴", "^{\\prime\\prime\\prime}"],
      ["≀", "\\wr"], ["⋆", "\\star"],
      ["∔", "\\dotplus"], ["⋉", "\\ltimes"], ["⋊", "\\rtimes"],
    ],
  },
  {
    id: "bigops",
    items: [
      ["Σ", "\\sum"], ["∫", "\\int"], ["Π", "\\prod"], ["∏", "\\coprod"],
      ["∬", "\\iint"], ["∭", "\\iiint"], ["⨌", "\\iiiint"], ["∮", "\\oint"],
      ["∯", "\\oiint"], ["∰", "\\oiiint"], ["⨋", "\\sumint"],
      ["⋂", "\\bigcap"], ["⋃", "\\bigcup"], ["⋀", "\\bigwedge"], ["⋁", "\\bigvee"],
      ["⨁", "\\bigoplus"], ["⨂", "\\bigotimes"], ["⨆", "\\bigsqcup"], ["⨄", "\\biguplus"],
      ["⨉", "\\bigtimes"], ["∐", "\\amalg"],
      ["⨍", "\\intsl"],
    ],
  },
  {
    id: "arrows",
    items: [
      ["→", "\\rightarrow"], ["←", "\\leftarrow"], ["⇒", "\\Rightarrow"], ["⇐", "\\Leftarrow"],
      ["↔", "\\leftrightarrow"], ["⇔", "\\Leftrightarrow"],
      ["↑", "\\uparrow"], ["↓", "\\downarrow"], ["↦", "\\mapsto"], ["⟼", "\\longmapsto"],
      ["⟶", "\\longrightarrow"], ["⟵", "\\longleftarrow"],
      ["⟹", "\\Longrightarrow"], ["⟸", "\\Longleftarrow"], ["⟺", "\\Longleftrightarrow"],
      ["↗", "\\nearrow"], ["↘", "\\searrow"], ["↙", "\\swarrow"], ["↖", "\\nwarrow"],
      ["⇗", "\\Nearrow"], ["⇘", "\\Searrow"], ["⇙", "\\Swarrow"], ["⇖", "\\Nwarrow"],
      ["↪", "\\hookrightarrow"], ["↩", "\\hookleftarrow"],
      ["↠", "\\twoheadrightarrow"], ["↣", "\\rightarrowtail"],
      ["⇄", "\\rightleftarrows"], ["⇆", "\\leftrightarrows"],
      ["⇉", "\\rightrightarrows"], ["⇇", "\\leftleftarrows"],
      ["⇌", "\\rightleftharpoons"], ["⇋", "\\leftrightharpoons"],
      ["↝", "\\leadsto"], ["⇝", "\\rightsquigarrow"],
      ["⇢", "\\dashrightarrow"], ["⇠", "\\dashleftarrow"],
      ["↺", "\\circlearrowleft"], ["↻", "\\circlearrowright"],
      ["↶", "\\curvearrowleft"], ["↷", "\\curvearrowright"],
      ["⇀", "\\rightharpoonup"], ["⇁", "\\rightharpoondown"],
      ["↾", "\\upharpoonright"], ["↿", "\\upharpoonleft"],
      ["⇃", "\\downharpoonright"], ["⇂", "\\downharpoonleft"],
      ["↤", "\\mapsfrom"], ["⟻", "\\longmapsfrom"],
      ["↫", "\\looparrowleft"], ["↬", "\\looparrowright"],
      ["↚", "\\nleftarrow"], ["↛", "\\nrightarrow"],
      ["⇍", "\\nLeftarrow"], ["⇏", "\\nRightarrow"],
      ["↮", "\\nleftrightarrow"],
    ],
  },
  {
    id: "sets",
    items: [
      ["∈", "\\in"], ["∉", "\\notin"], ["∋", "\\ni"], ["∌", "\\notni"],
      ["∅", "\\emptyset"], ["∅", "\\varnothing"],
      ["∀", "\\forall"], ["∃", "\\exists"], ["∄", "\\nexists"], ["¬", "\\neg"],
      ["∧", "\\land"], ["∨", "\\lor"], ["⟹", "\\implies"], ["⟺", "\\iff"],
      ["∴", "\\therefore"], ["∵", "\\because"],
      ["∁", "\\complement"], ["幂集", "\\mathcal{P}(#?)", "Power set"],
      ["补集", "#?^{c}", "Complement"],
      ["指示函数", "\\mathbf{1}_{#?}", "Indicator function"],
      ["对称差", "#? \\triangle #?", "Symmetric difference"],
      ["基数", "|#?|", "Cardinality"],
      ["ℝ", "\\mathbb{R}"], ["ℕ", "\\mathbb{N}"], ["ℤ", "\\mathbb{Z}"], ["ℚ", "\\mathbb{Q}"],
      ["ℂ", "\\mathbb{C}"], ["ℙ", "\\mathbb{P}"], ["ℍ", "\\mathbb{H}"],
      ["集族", "\\{#?\\}_{#?\\in #?}", "Family of sets"],
      ["集列上极限", "\\limsup_{n\\to\\infty} #?", "Set limsup"],
      ["集列下极限", "\\liminf_{n\\to\\infty} #?", "Set liminf"],
      ["包含排斥", "|A\\cup B| = |A|+|B|-|A\\cap B|", "Inclusion-exclusion"],
      ["康托尔", "\\mathfrak{c} = 2^{\\aleph_0}", "Continuum"],
      ["⊤", "\\top"], ["⊥", "\\bot"],
    ],
  },
  {
    id: "functions",
    items: [
      ["sin", "\\sin"], ["cos", "\\cos"], ["tan", "\\tan"],
      ["log", "\\log"], ["ln", "\\ln"], ["lg", "\\lg"], ["exp", "\\exp"],
      ["lim", "\\lim"], ["max", "\\max"], ["min", "\\min"], ["sup", "\\sup"], ["inf", "\\inf"],
      ["argmax", "\\arg\\max"], ["argmin", "\\arg\\min"],
      ["sin⁻¹", "\\sin^{-1}"], ["cos⁻¹", "\\cos^{-1}"], ["tan⁻¹", "\\tan^{-1}"],
      ["sec", "\\sec"], ["csc", "\\csc"], ["cot", "\\cot"],
      ["arcsin", "\\arcsin"], ["arccos", "\\arccos"], ["arctan", "\\arctan"],
      ["sinh", "\\sinh"], ["cosh", "\\cosh"], ["tanh", "\\tanh"], ["coth", "\\coth"],
      ["sech", "\\operatorname{sech}"], ["csch", "\\operatorname{csch}"],
      ["det", "\\det"], ["dim", "\\dim"], ["gcd", "\\gcd"], ["lcm", "\\operatorname{lcm}"],
      ["arg", "\\arg"], ["deg", "\\deg"], ["ker", "\\ker"], ["hom", "\\hom"],
      ["Pr", "\\Pr"], ["sgn", "\\operatorname{sgn}"],
      ["mod", "\\bmod"], ["pmod", "\\pmod{#?}"],
      ["Re", "\\operatorname{Re}(#?)", "Real part"],
      ["Im", "\\operatorname{Im}(#?)", "Imaginary part"],
      ["cis", "\\operatorname{cis}(#?)", "cis"],
      ["sinc", "\\operatorname{sinc}(#?)", "Sinc"],
      ["rank", "\\operatorname{rank}"], ["span", "\\operatorname{span}"], ["tr", "\\operatorname{tr}"],
      ["erf", "\\operatorname{erf}"], ["erfc", "\\operatorname{erfc}"], ["erfi", "\\operatorname{erfi}"],
      ["Si", "\\operatorname{Si}(#?)", "Sine integral"],
      ["Ci", "\\operatorname{Ci}(#?)", "Cosine integral"],
      ["Ei", "\\operatorname{Ei}(#?)", "Exponential integral"],
      ["多对数", "\\operatorname{Li}_s(#?)", "Polylog"],
      ["Euler φ", "\\varphi(n)", "Euler totient"],
    ],
  },
  {
    id: "probability",
    structures: true,
    items: [
      ["概率", "\\mathbb{P}(#?)", "Probability"],
      ["期望", "\\mathbb{E}[#?]", "Expectation"],
      ["方差", "\\operatorname{Var}(#?)", "Variance"],
      ["标准差", "\\sigma(#?)", "Standard deviation"],
      ["协方差", "\\operatorname{Cov}(#?,#?)", "Covariance"],
      ["相关系数", "\\operatorname{Corr}(#?,#?)", "Correlation"],
      ["协方差矩阵", "\\Sigma", "Covariance matrix"],
      ["条件期望", "\\mathbb{E}[#?\\mid #?]", "Conditional expectation"],
      ["条件方差", "\\operatorname{Var}(#?\\mid #?)", "Conditional variance"],
      ["矩", "\\mathbb{E}[#?^{k}]", "Moment"],
      ["中心矩", "\\mathbb{E}[(#?-\\mu)^{k}]", "Central moment"],
      ["正态", "\\mathcal{N}(#?,#?)", "Normal distribution"],
      ["伯努利", "\\operatorname{Bernoulli}(#?)", "Bernoulli distribution"],
      ["二项", "\\operatorname{Bin}(#?,#?)", "Binomial distribution"],
      ["泊松", "\\operatorname{Poisson}(#?)", "Poisson distribution"],
      ["均匀", "\\operatorname{Uniform}(#?,#?)", "Uniform distribution"],
      ["指数", "\\operatorname{Exp}(#?)", "Exponential distribution"],
      ["几何", "\\operatorname{Geom}(#?)", "Geometric distribution"],
      ["多项", "\\operatorname{Multinomial}(#?,\\ldots)", "Multinomial distribution"],
      ["对数正态", "\\operatorname{LogNormal}(#?,#?)", "Log-normal distribution"],
      ["伽马", "\\Gamma(#?)", "Gamma distribution"],
      ["贝塔", "\\operatorname{Beta}(#?,#?)", "Beta distribution"],
      ["卡方", "\\chi^2_{(#?)}", "Chi-squared"],
      ["t 分布", "t_{(#?)}", "Student t"],
      ["F 分布", "F_{(#?,#?)}", "F-distribution"],
      ["条件", "#? \\mid #?", "Conditional bar"],
      ["独立", "#? \\perp\\!\\!\\!\\perp #?", "Independence"],
      ["贝叶斯", "\\mathbb{P}(A|B) = \\frac{\\mathbb{P}(B|A)\\mathbb{P}(A)}{\\mathbb{P}(B)}", "Bayes theorem"],
      ["似然", "\\mathcal{L}(#?;#?)", "Likelihood"],
      ["信息熵", "H(#?) = -\\sum p_i\\log p_i", "Entropy"],
      ["KL 散度", "D_{\\mathrm{KL}}(#?\\|#?)", "KL divergence"],
      ["互信息", "I(#?;#?)", "Mutual information"],
      ["特征函数", "\\varphi_{#?}(t) = \\mathbb{E}[e^{it#?}]", "Characteristic function"],
      ["生成函数", "M_{#?}(t) = \\mathbb{E}[e^{t#?}]", "Moment generating function"],
      ["大数定律", "\\bar{X}_n \\xrightarrow{p} \\mu", "Law of large numbers"],
      ["中心极限", "\\sqrt{n}(\\bar{X}_n-\\mu) \\xrightarrow{d} \\mathcal{N}(0,\\sigma^2)", "Central limit theorem"],
      ["马尔可夫", "\\mathbb{P}(X\\ge a) \\le \\frac{\\mathbb{E}[X]}{a}", "Markov inequality"],
      ["切比雪夫", "\\mathbb{P}(|X-\\mu|\\ge k\\sigma) \\le \\frac{1}{k^2}", "Chebyshev inequality"],
      ["超几何", "\\operatorname{Hypergeometric}(N,K,n)", "Hypergeometric"],
      ["Weibull", "\\operatorname{Weibull}(\\lambda,k)", "Weibull distribution"],
      ["Dirichlet", "\\operatorname{Dir}(\\alpha_1,\\ldots,\\alpha_k)", "Dirichlet distribution"],
      ["Cauchy", "\\operatorname{Cauchy}(x_0,\\gamma)", "Cauchy distribution"],
      ["顺序统计量", "X_{(k)}", "Order statistic"],
      ["经验分布", "F_n(x) = \\frac1n\\sum_{i=1}^n \\mathbf{1}_{\\{X_i\\le x\\}}", "Empirical CDF"],
      ["置信区间", "\\bar{X} \\pm z_{\\alpha/2}\\frac{\\sigma}{\\sqrt{n}}", "Confidence interval"],
      ["风险率", "h(t) = \\frac{f(t)}{1-F(t)}", "Hazard rate"],
      ["随机过程", "\\{X_t\\}_{t\\in T}", "Stochastic process"],
      ["马尔可夫链", "\\mathbb{P}(X_{n+1}=j\\mid X_n=i) = p_{ij}", "Markov chain"],
      ["泊松过程", "N_t \\sim \\operatorname{Pois}(\\lambda t)", "Poisson process"],
      ["布朗运动", "B_t \\sim \\mathcal{N}(0,t)", "Brownian motion"],
      ["鞅", "\\mathbb{E}[X_{t+s}\\mid\\mathcal{F}_t] = X_t", "Martingale"],
      ["停时", "\\tau = \\inf\\{t: X_t \\in A\\}", "Stopping time"],
      ["随机游走", "S_n = X_1 + \\cdots + X_n", "Random walk"],
      ["Itô 积分", "\\int_0^t X_s\\,dB_s", "Ito integral"],
      ["Itô 引理", "df = \\left(\\frac{\\partial f}{\\partial t}+\\mu\\frac{\\partial f}{\\partial x}+\\frac12\\sigma^2\\frac{\\partial^2 f}{\\partial x^2}\\right)dt + \\sigma\\frac{\\partial f}{\\partial x}dB", "Ito lemma"],
      ["随机微分方程", "dX_t = \\mu(X_t,t)dt + \\sigma(X_t,t)dB_t", "SDE"],
      ["Kolmogorov 方程", "\\frac{\\partial p}{\\partial t} = -\\frac{\\partial}{\\partial x}(\\mu p) + \\frac12\\frac{\\partial^2}{\\partial x^2}(\\sigma^2 p)", "Kolmogorov eqn"],
      ["Feynman-Kac", "u(x,t) = \\mathbb{E}\\left[e^{-\\int_t^T r\\,ds}\\varphi(X_T)\\mid X_t=x\\right]", "Feynman-Kac"],
      ["二次变分", "[X,X]_t = \\lim_{|\\Pi|\\to0}\\sum_{i}(X_{t_i}-X_{t_{i-1}})^2", "Quadratic variation"],
      ["遍历定理", "\\frac1T\\int_0^T X_t\\,dt \\xrightarrow{a.s.} \\mathbb{E}[X_0]", "Ergodic theorem"],
      ["Doob 停时", "\\mathbb{E}[X_\\tau] = \\mathbb{E}[X_0]", "Doob optional stopping"],
      ["大偏差", "\\mathbb{P}(\\bar X_n > a) \\asymp e^{-nI(a)}", "Large deviation"],
    ],
  },
  {
    id: "physics",
    structures: true,
    items: [
      ["牛顿第二定律", "\\mathbf{F} = m\\mathbf{a}", "Newton 2nd"],
      ["动能", "E_k = \\frac{1}{2}mv^2", "Kinetic energy"],
      ["动量", "\\mathbf{p} = m\\mathbf{v}", "Momentum"],
      ["角动量", "\\mathbf{L} = \\mathbf{r}\\times\\mathbf{p}", "Angular momentum"],
      ["扭矩", "\\boldsymbol{\\tau} = \\mathbf{r}\\times\\mathbf{F}", "Torque"],
      ["转动惯量", "I = \\int r^2\\,dm", "Moment of inertia"],
      ["角速度", "\\omega = \\frac{d\\theta}{dt}", "Angular velocity"],
      ["向心加速度", "a_c = \\frac{v^2}{r}", "Centripetal acceleration"],
      ["功", "W = \\int \\mathbf{F}\\cdot d\\mathbf{r}", "Work"],
      ["功率", "P = \\frac{dW}{dt} = \\mathbf{F}\\cdot\\mathbf{v}", "Power"],
      ["万有引力", "F = G\\frac{m_1 m_2}{r^2}", "Gravity"],
      ["引力势能", "U = -\\frac{GMm}{r}", "Gravitational potential"],
      ["胡克定律", "F = -k x", "Hooke law"],
      ["弹簧势能", "U = \\frac{1}{2}kx^2", "Spring potential"],
      ["简谐运动", "x(t) = A\\cos(\\omega t + \\phi)", "SHM"],
      ["简谐周期", "T = 2\\pi\\sqrt{\\frac{m}{k}}", "SHM period"],
      ["单摆周期", "T = 2\\pi\\sqrt{\\frac{L}{g}}", "Pendulum period"],
      ["欧姆定律", "V = IR", "Ohm law"],
      ["功率电学", "P = I^2 R = IV", "Electric power"],
      ["焦耳定律", "P = I^2 R", "Joule heating"],
      ["电容", "C = \\frac{Q}{V}", "Capacitance"],
      ["RC 充电", "V(t) = V_0(1-e^{-t/RC})", "RC charging"],
      ["RC 放电", "V(t) = V_0e^{-t/RC}", "RC discharging"],
      ["电感", "\\mathcal{E} = -L\\frac{dI}{dt}", "Inductance"],
      ["库仑定律", "F = k_e\\frac{q_1 q_2}{r^2}", "Coulomb law"],
      ["电场", "\\mathbf{E} = \\frac{\\mathbf{F}}{q}", "Electric field"],
      ["电势", "V = -\\int \\mathbf{E}\\cdot d\\mathbf{l}", "Electric potential"],
      ["电偶极矩", "\\mathbf{p} = q\\mathbf{d}", "Dipole moment"],
      ["高斯定律", "\\oint \\mathbf{E}\\cdot d\\mathbf{A} = \\frac{Q}{\\varepsilon_0}", "Gauss law"],
      ["法拉第定律", "\\mathcal{E} = -\\frac{d\\Phi_B}{dt}", "Faraday law"],
      ["安培定律", "\\oint \\mathbf{B}\\cdot d\\mathbf{l} = \\mu_0 I", "Ampere law"],
      ["毕奥-萨伐尔", "d\\mathbf{B} = \\frac{\\mu_0}{4\\pi}\\frac{I\\,d\\mathbf{l}\\times\\hat{r}}{r^2}", "Biot-Savart law"],
      ["洛伦兹力", "\\mathbf{F} = q(\\mathbf{E} + \\mathbf{v}\\times\\mathbf{B})", "Lorentz force"],
      ["磁矢势", "\\mathbf{B} = \\nabla\\times\\mathbf{A}", "Magnetic vector potential"],
      ["麦克斯韦", "\\nabla\\cdot\\mathbf{E}=\\frac{\\rho}{\\varepsilon_0},\\; \\nabla\\cdot\\mathbf{B}=0,\\; \\nabla\\times\\mathbf{E}=-\\frac{\\partial\\mathbf{B}}{\\partial t},\\; \\nabla\\times\\mathbf{B}=\\mu_0\\mathbf{J}+\\mu_0\\varepsilon_0\\frac{\\partial\\mathbf{E}}{\\partial t}", "Maxwell eqns"],
      ["理想气体", "PV = nRT", "Ideal gas law"],
      ["热力学第一定律", "\\Delta U = Q - W", "1st law thermo"],
      ["熵", "dS = \\frac{dQ_{\\text{rev}}}{T}", "Entropy"],
      ["玻尔兹曼", "S = k_B \\ln W", "Boltzmann entropy"],
      ["热容", "Q = mc\\Delta T", "Heat capacity"],
      ["潜热", "Q = mL", "Latent heat"],
      ["卡诺效率", "\\eta_C = 1 - \\frac{T_c}{T_h}", "Carnot efficiency"],
      ["自由能", "F = U - TS", "Helmholtz free energy"],
      ["吉布斯自由能", "G = H - TS", "Gibbs free energy"],
      ["焓", "H = U + PV", "Enthalpy"],
      ["伯努利", "P + \\frac12\\rho v^2 + \\rho gh = \\text{const}", "Bernoulli eqn"],
      ["浮力", "F_b = \\rho gV", "Buoyancy"],
      ["连续性", "A_1v_1 = A_2v_2", "Continuity eqn"],
      ["薛定谔方程", "i\\hbar\\frac{\\partial}{\\partial t}\\Psi = \\hat{H}\\Psi", "Schrodinger eqn"],
      ["质能方程", "E = mc^2", "Mass-energy"],
      ["不确定性", "\\Delta x\\,\\Delta p \\geq \\frac{\\hbar}{2}", "Uncertainty"],
      ["光电效应", "E_{\\text{max}} = h\\nu - \\phi", "Photoelectric"],
      ["德布罗意", "\\lambda = \\frac{h}{p}", "de Broglie"],
      ["黑体辐射", "I(\\nu,T) = \\frac{2h\\nu^3}{c^2}\\frac{1}{e^{h\\nu/k_B T}-1}", "Planck law"],
      ["衰变定律", "N(t) = N_0e^{-\\lambda t}", "Decay law"],
      ["半衰期", "T_{1/2} = \\frac{\\ln 2}{\\lambda}", "Half-life"],
      ["折射定律", "n_1\\sin\\theta_1 = n_2\\sin\\theta_2", "Snell law"],
      ["多普勒", "f' = f\\frac{c \\pm v_r}{c \\mp v_s}", "Doppler effect"],
      ["杨氏双缝", "d\\sin\\theta = m\\lambda", "Young double-slit"],
      ["相对论动量", "E^2 = (pc)^2 + (mc^2)^2", "Energy-momentum"],
      ["拉格朗日量", "L = T - V", "Lagrangian"],
      ["哈密顿量", "H = T + V = \\sum p_i\\dot q_i - L", "Hamiltonian"],
      ["作用量", "S = \\int L\\,dt", "Action"],
      ["诺特定理", "\\partial_\\mu j^\\mu = 0", "Noether theorem"],
      ["Lorentz 因子", "\\gamma = \\frac{1}{\\sqrt{1-v^2/c^2}}", "Lorentz factor"],
      ["四维间隔", "ds^2 = -c^2dt^2 + dx^2 + dy^2 + dz^2", "Spacetime interval"],
      ["达朗贝尔", "\\square = \\partial_\\mu\\partial^\\mu", "d'Alembertian"],
      ["Klein-Gordon", "(\\square + m^2)\\phi = 0", "Klein-Gordon eqn"],
      ["Dirac 方程", "(i\\gamma^\\mu\\partial_\\mu - m)\\psi = 0", "Dirac equation"],
      ["精细结构", "\\alpha = \\frac{e^2}{4\\pi\\varepsilon_0\\hbar c}", "Fine structure"],
      ["康普顿", "\\lambda' - \\lambda = \\frac{h}{mc}(1-\\cos\\theta)", "Compton scattering"],
      ["标准模型", "\\mathrm{SU}(3)_C\\times\\mathrm{SU}(2)_L\\times\\mathrm{U}(1)_Y", "Standard model"],
      ["Pauli 矩阵", "\\sigma_1 = \\begin{pmatrix}0&1\\\\1&0\\end{pmatrix}", "Pauli matrix"],
      ["Gamma 矩阵", "\\{\\gamma^\\mu,\\gamma^\\nu\\} = 2\\eta^{\\mu\\nu}", "Gamma matrices"],
      ["热传导", "\\frac{dQ}{dt} = -kA\\frac{dT}{dx}", "Heat conduction"],
      ["斯特藩-玻尔兹曼", "j = \\sigma T^4", "Stefan-Boltzmann law"],
      ["费米-狄拉克", "f(E) = \\frac{1}{e^{(E-\\mu)/kT}+1}", "Fermi-Dirac"],
      ["玻色-爱因斯坦", "f(E) = \\frac{1}{e^{(E-\\mu)/kT}-1}", "Bose-Einstein"],
      ["质量亏损", "\\Delta E = \\Delta m\\,c^2", "Mass defect"],
      ["透镜方程", "\\frac{1}{f} = \\frac{1}{u} + \\frac{1}{v}", "Lens equation"],
      ["瑞利判据", "\\theta = 1.22\\frac{\\lambda}{D}", "Rayleigh criterion"],
      ["玻尔半径", "a_0 = \\frac{4\\pi\\varepsilon_0\\hbar^2}{m_e e^2}", "Bohr radius"],
      ["里德伯公式", "\\frac{1}{\\lambda} = R\\!\\left(\\frac{1}{n_1^2}-\\frac{1}{n_2^2}\\right)", "Rydberg formula"],
      ["玻尔模型", "E_n = -\\frac{13.6\\,\\mathrm{eV}}{n^2}", "Bohr model"],
    ],
  },
  {
    id: "chemistry",
    structures: true,
    items: [
      ["化学式", "\\ce{ #? }", "Formula"],
      ["反应式", "\\ce{ #? -> #? }", "Reaction"],
      ["可逆", "\\ce{ #? <=> #? }", "Reversible"],
      ["共振", "\\ce{ #? <-> #? }", "Resonance"],
      ["上下箭头", "\\ce{ #? ->[#?][#?] #? }", "Arrow with text"],
      ["H₂O", "\\ce{H2O}", "Water"],
      ["CO₂", "\\ce{CO2}", "Carbon dioxide"],
      ["O₂", "\\ce{O2}", "Oxygen"],
      ["NaCl", "\\ce{NaCl}", "Sodium chloride"],
      ["HCl", "\\ce{HCl}", "Hydrochloric acid"],
      ["HNO₃", "\\ce{HNO3}", "Nitric acid"],
      ["H₂SO₄", "\\ce{H2SO4}", "Sulfuric acid"],
      ["CH₄", "\\ce{CH4}", "Methane"],
      ["C₂H₅OH", "\\ce{C2H5OH}", "Ethanol"],
      ["C₆H₆", "\\ce{C6H6}", "Benzene"],
      ["CH₃COOH", "\\ce{CH3COOH}", "Acetic acid"],
      ["NH₃", "\\ce{NH3}", "Ammonia"],
      ["NaOH", "\\ce{NaOH}", "Sodium hydroxide"],
      ["H₂O₂", "\\ce{H2O2}", "Hydrogen peroxide"],
      ["KMnO₄", "\\ce{KMnO4}", "Potassium permanganate"],
      ["H⁺", "\\ce{H+}", "Proton"],
      ["OH⁻", "\\ce{OH-}", "Hydroxide"],
      ["SO₄²⁻", "\\ce{SO4^2-}", "Sulfate"],
      ["NO₃⁻", "\\ce{NO3-}", "Nitrate"],
      ["CO₃²⁻", "\\ce{CO3^2-}", "Carbonate"],
      ["NH₄⁺", "\\ce{NH4+}", "Ammonium"],
      ["Fe²⁺", "\\ce{Fe^2+}", "Iron(II)"],
      ["Fe³⁺", "\\ce{Fe^3+}", "Iron(III)"],
      ["→", "\\rightarrow"], ["⇌", "\\rightleftharpoons"], ["↑", "\\uparrow"], ["↓", "\\downarrow"],
      ["aq", "\\mathrm{(aq)}"], ["s", "\\mathrm{(s)}"], ["l", "\\mathrm{(l)}"], ["g", "\\mathrm{(g)}"],
      ["pH", "\\mathrm{pH} = -\\log[\\ce{H+}]", "pH"],
      ["pOH", "\\mathrm{pOH} = -\\log[\\ce{OH-}]", "pOH"],
      ["Kw", "K_w = [\\ce{H+}][\\ce{OH-}] = 10^{-14}", "Kw"],
      ["Ka", "K_a = \\frac{[\\ce{H+}][\\ce{A-}]}{[\\ce{HA}]}", "Ka"],
      ["Henderson-Hasselbalch", "\\mathrm{pH} = \\mathrm{p}K_a + \\log\\frac{[\\ce{A-}]}{[\\ce{HA}]}", "Henderson-Hasselbalch"],
      ["平衡常数", "K_c = \\frac{[\\ce{C}]^c[\\ce{D}]^d}{[\\ce{A}]^a[\\ce{B}]^b}", "Equilibrium constant"],
      ["反应商", "Q = \\frac{[\\ce{C}]^c[\\ce{D}]^d}{[\\ce{A}]^a[\\ce{B}]^b}", "Reaction quotient"],
      ["ΔH", "\\Delta H", "Enthalpy change"],
      ["ΔS", "\\Delta S", "Entropy change"],
      ["ΔG", "\\Delta G = \\Delta H - T\\Delta S", "Gibbs free energy"],
      ["能斯特", "E = E^\\circ - \\frac{RT}{nF}\\ln Q", "Nernst equation"],
      ["Arrhenius", "k = Ae^{-E_a/RT}", "Arrhenius eqn"],
      ["速率方程", "\\text{rate} = k[\\ce{A}]^m[\\ce{B}]^n", "Rate law"],
      ["Beer-Lambert", "A = \\varepsilon cl", "Beer-Lambert law"],
      ["电子组态", "1s^2\\,2s^2\\,2p^6\\,3s^2\\,3p^6", "Electron config"],
      ["sp³ 杂化", "\\ce{CH4} \\text{ sp}^3", "sp3 hybridization"],
      ["sp² 杂化", "\\ce{C2H4} \\text{ sp}^2", "sp2 hybridization"],
      ["半反应", "\\ce{oxid + ne- -> red}", "Half-reaction"],
      ["法拉第常数", "F = 96485\\,\\mathrm{C\\,mol^{-1}}", "Faraday constant"],
      ["ΔG°", "\\Delta G^\\circ = -RT\\ln K", "Standard Gibbs"],
      ["van't Hoff", "\\ln\\frac{K_2}{K_1} = -\\frac{\\Delta H^\\circ}{R}\\left(\\frac1{T_2}-\\frac1{T_1}\\right)", "van't Hoff eqn"],
      ["Clapeyron", "\\frac{dP}{dT} = \\frac{\\Delta S}{\\Delta V}", "Clapeyron eqn"],
      ["Langmuir", "\\theta = \\frac{KP}{1+KP}", "Langmuir isotherm"],
      ["量子产率", "\\Phi = \\frac{k_r}{k_r + k_{nr}}", "Quantum yield"],
    ],
  },
  {
    id: "accents",
    items: [
      ["𝐱", "\\mathbf{#?}"], ["ℝ", "\\mathbb{#?}"], ["𝓧", "\\mathcal{#?}"],
      ["𝓛", "\\mathscr{#?}"], ["𝖠", "\\mathsf{#?}"], ["𝚃", "\\mathtt{#?}"],
      ["x̂", "\\hat{x}"], ["x̄", "\\bar{x}"], ["x̃", "\\tilde{x}"], ["x⃗", "\\vec{x}"],
      ["ẋ", "\\dot{x}"], ["ẍ", "\\ddot{x}"],
      ["x̲", "\\underline{x}"], ["x̅", "\\overline{x}"],
      ["𝜶", "\\boldsymbol{#?}", "boldsymbol"],
      ["x̂̅", "\\widehat{#?}", "Wide hat"],
      ["x̃̅", "\\widetilde{#?}", "Wide tilde"],
      ["x̀", "\\grave{x}"], ["x́", "\\acute{x}"],
      ["x̌", "\\check{x}"], ["x̆", "\\breve{x}"], ["x̊", "\\mathring{x}"],
      ["𝑥", "\\mathit{#?}"], ["𝔁", "\\mathfrak{#?}"],
      ["text", "\\text{#?}"], ["rm", "\\mathrm{#?}"],
      ["ı", "\\imath"], ["ȷ", "\\jmath"],
      ["\\slashed{#?}", "\\slashed{#?}", "Feynman slash"],
      ["\\bm{}", "\\bm{#?}", "Bold math"],
    ],
  },
  {
    id: "misc",
    items: [
      ["⋯", "\\cdots"], ["…", "\\dots"], ["⋮", "\\vdots"], ["⋱", "\\ddots"],
      ["∞", "\\infty"], ["ℏ", "\\hbar"], ["ℓ", "\\ell"],
      ["∠", "\\angle"], ["∡", "\\measuredangle"], ["∢", "\\sphericalangle"],
      ["°", "^\\circ"], ["ℜ", "\\Re"], ["ℑ", "\\Im"], ["℘", "\\wp"],
      ["ı", "\\imath"], ["ȷ", "\\jmath"],
      ["△", "\\triangle"], ["□", "\\Box"], ["◇", "\\Diamond"],
      ["■", "\\blacksquare"], ["▲", "\\blacktriangle"], ["◆", "\\blacklozenge"],
      ["♠", "\\spadesuit"], ["♥", "\\heartsuit"], ["♣", "\\clubsuit"], ["♦", "\\diamondsuit"],
      ["★", "\\bigstar"], ["♮", "\\natural"], ["♭", "\\flat"], ["♯", "\\sharp"],
      ["✓", "\\checkmark"], ["✗", "\\times"], ["§", "\\S"], ["¶", "\\P"],
      ["©", "\\copyright"], ["®", "\\circledR"], ["¥", "\\yen"], ["£", "\\pounds"],
      ["µ", "\\textmu"], ["ð", "\\eth"], ["Ⅎ", "\\Finv"], ["⅁", "\\Game"],
      ["†", "\\dag"], ["‡", "\\ddag"],
      ["℃", "\\textcelsius"], ["℉", "\\textfahrenheit"],
      ["⌀", "\\diameter"], ["⚠", "\\textwarning"],
    ],
  },
];

let mathfield = null;
let locale = "zh";
let mode = "insert";
let pendingInit = null;

const host = document.getElementById("mathfieldHost");
const latexSource = document.getElementById("latexSource");
const statusText = document.getElementById("statusText");
const cancelButton = document.getElementById("cancelButton");
const acceptButton = document.getElementById("acceptButton");
const tabs = document.getElementById("libraryTabs");
const titleText = document.getElementById("libraryTitleText");
const grid = document.getElementById("symbolGrid");
const searchInput = document.getElementById("symbolSearch");
const globalSearch = document.getElementById("globalSearch");

function strings() {
  return locale.startsWith("zh") ? STRINGS.zh : STRINGS.en;
}

function displayLabel(item) {
  if (locale.startsWith("zh")) {
    return item[0];
  }

  return item[2] || item[0];
}

function groupTitle(group) {
  return strings().tabs[group.id] || group.id;
}

function send(message) {
  window.chrome?.webview?.postMessage(message);
}

function setStatus(text) {
  statusText.textContent = text || "";
}

function currentLatex() {
  const source = latexSource.value.trim();
  if (isMathMlSource(source)) {
    return source;
  }

  return mathfield?.getValue("latex-expanded")?.trim() || "";
}

function syncSource() {
  latexSource.value = currentLatex();
}

function setLatex(latex) {
  const source = latex || "";
  if (isMathMlSource(source.trim())) {
    latexSource.value = source;
    mathfield.setValue("", { silenceNotifications: true });
    return;
  }

  mathfield.setValue(source, { silenceNotifications: true });
  syncSource();
}

function isMathMlSource(source) {
  return /^<math(\s|>|:)/i.test(source);
}

function insertLatex(latex) {
  if (latex.startsWith("matrix:")) {
    insertMatrix(latex.slice("matrix:".length));
    return;
  }

  mathfield.insert(latex, { format: "latex" });
  mathfield.focus();
  syncSource();
}

function insertMatrix(env, rows = 2, cols = 2) {
  if (env === "cases") {
    cols = 2;
  }

  if (env === "hessian") {
    const body = Array.from({ length: rows }, (_, i) =>
      Array.from({ length: cols }, (_, j) =>
        `\\frac{\\partial^2 #?}{\\partial #?_{${i + 1}}\\partial #?_{${j + 1}}}`
      ).join(" & ")
    ).join(" \\\\ ");
    mathfield.insert(`\\begin{bmatrix} ${body} \\end{bmatrix}`, { format: "latex" });
    mathfield.focus();
    syncSource();
    return;
  }

  const body = Array.from({ length: rows }, () => Array.from({ length: cols }, () => "#?").join(" & ")).join(" \\\\ ");
  mathfield.insert(`\\begin{${env}} ${body} \\end{${env}}`, { format: "latex" });
  mathfield.focus();
  syncSource();
}

let _currentGroup = null;

function selectGroup(group) {
  _currentGroup = group;
  searchInput.value = "";
  for (const button of tabs.querySelectorAll("button")) {
    button.classList.toggle("active", button.dataset.group === group.id);
  }

  titleText.textContent = groupTitle(group);
  renderGrid(group, "");
}

function renderGrid(group, query) {
  grid.className = group.structures ? "symbol-grid structures" : "symbol-grid";
  grid.replaceChildren();
  const q = query.trim().toLowerCase();
  for (const item of group.items) {
    if (q && !matchItem(item, q)) continue;

    if (group.structures && String(item[1]).startsWith("matrix:")) {
      grid.appendChild(createMatrixControl(displayLabel(item), item[1].slice("matrix:".length)));
      continue;
    }

    const button = document.createElement("button");
    button.type = "button";
    button.textContent = displayLabel(item);
    button.title = item[2] ? `${item[2]}\n${item[1]}` : item[1];
    button.addEventListener("click", () => insertLatex(item[1]));
    grid.appendChild(button);
  }
}

function matchItem(item, query) {
  const label = displayLabel(item).toLowerCase();
  const latex = item[1].toLowerCase();
  return label.includes(query) || latex.includes(query);
}

searchInput.addEventListener("input", () => {
  if (_currentGroup) renderGrid(_currentGroup, searchInput.value);
});

function renderGlobalResults(query) {
  const q = query.trim().toLowerCase();
  if (!q) { selectGroup(_currentGroup || GROUPS[0]); return; }
  grid.className = "symbol-grid structures";
  grid.replaceChildren();
  for (const group of GROUPS) {
    const hits = group.items.filter(item => matchItem(item, q));
    if (!hits.length) continue;
    const label = document.createElement("div");
    label.className = "global-group-label";
    label.textContent = groupTitle(group);
    grid.appendChild(label);
    for (const item of hits) {
      if (group.structures && String(item[1]).startsWith("matrix:")) {
        grid.appendChild(createMatrixControl(displayLabel(item), item[1].slice("matrix:".length)));
        continue;
      }
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = displayLabel(item);
      button.title = item[2] ? `${item[2]}\n${item[1]}` : item[1];
      button.addEventListener("click", () => insertLatex(item[1]));
      grid.appendChild(button);
    }
  }
}

globalSearch.addEventListener("input", () => {
  renderGlobalResults(globalSearch.value);
});

function createMatrixControl(label, env) {
  const isCases = env === "cases";
  const row = document.createElement("div");
  row.className = isCases ? "matrix-row cases" : "matrix-row";

  const rowSelect = document.createElement("select");
  rowSelect.title = strings().rows;
  for (let i = 1; i <= 10; i++) {
    rowSelect.appendChild(new Option(String(i), String(i), i === 2, i === 2));
  }
  row.appendChild(rowSelect);

  let colSelect = null;
  if (!isCases) {
    colSelect = document.createElement("select");
    colSelect.title = strings().columns;
    for (let i = 1; i <= 10; i++) {
      colSelect.appendChild(new Option(String(i), String(i), i === 2, i === 2));
    }
    row.appendChild(colSelect);
  }

  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.title = `\\begin{${env}}...\\end{${env}}`;
  button.addEventListener("click", () => {
    insertMatrix(env, Number(rowSelect.value), colSelect ? Number(colSelect.value) : 2);
  });
  row.appendChild(button);
  return row;
}

function buildLibrary() {
  tabs.replaceChildren();
  for (const group of GROUPS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tab";
    button.dataset.group = group.id;
    button.textContent = groupTitle(group);
    button.title = groupTitle(group);
    button.addEventListener("click", () => selectGroup(group));
    tabs.appendChild(button);
  }

  selectGroup(GROUPS[0]);
}

function accept() {
  const latex = currentLatex();
  if (!latex) {
    setStatus(strings().latexRequired);
    return;
  }

  send({ type: "accept", latex, display: true });
}

function hideVirtualKeyboard() {
  window.mathVirtualKeyboard?.hide();
  mathfield?.focus();
}

function configureText() {
  document.documentElement.lang = locale.startsWith("zh") ? "zh-CN" : "en";
  cancelButton.textContent = strings().cancel;
  acceptButton.textContent = mode === "update" ? strings().acceptUpdate : strings().acceptInsert;
  setStatus(strings().ready);
  buildLibrary();
}

function applyInit(payload) {
  locale = String(payload?.locale || "zh").toLowerCase();
  mode = payload?.mode === "update" ? "update" : "insert";
  configureText();
  setLatex(payload?.latex || "");
  mathfield?.focus();
}

async function bootstrap() {
  MathfieldElement.fontsDirectory = new URL("./vendor/fonts", window.location.href).href;
  mathfield = new MathfieldElement();
  mathfield.smartFence = true;
  mathfield.smartMode = false;
  mathfield.mathVirtualKeyboardPolicy = "onfocus";
  mathfield.defaultMode = "math";
  host.appendChild(mathfield);
  mathfield.addEventListener("input", syncSource);
  latexSource.addEventListener("input", () => {
    const source = latexSource.value || "";
    if (!isMathMlSource(source.trim())) {
      mathfield.setValue(source, { silenceNotifications: true });
    }

    mathfield.focus();
  });
  cancelButton.addEventListener("click", () => send({ type: "cancel" }));
  acceptButton.addEventListener("click", accept);
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      hideVirtualKeyboard();
      return;
    }

    if (event.key === "Enter" && !event.isComposing && !event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
      event.preventDefault();
      accept();
    }
  });
  configureText();
  if (pendingInit || window.__latexSnipperPendingInit) {
    applyInit(pendingInit || window.__latexSnipperPendingInit);
    pendingInit = null;
    window.__latexSnipperPendingInit = null;
  }
  mathfield.focus();
}

window.LaTeXSnipperEditor = {
  init(payload) {
    pendingInit = payload;
    if (mathfield) {
      applyInit(payload);
      pendingInit = null;
    }
  },
};

bootstrap().catch((error) => setStatus(String(error)));
