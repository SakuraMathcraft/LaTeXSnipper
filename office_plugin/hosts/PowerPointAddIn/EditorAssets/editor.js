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
      ["υ", "\\upsilon"], ["χ", "\\chi"], ["ψ", "\\psi"], ["ϑ", "\\vartheta"], ["ϕ", "\\varphi"],
      ["ϵ", "\\varepsilon"], ["ϖ", "\\varpi"], ["ϱ", "\\varrho"], ["ς", "\\varsigma"],
      ["Γ", "\\Gamma"], ["Δ", "\\Delta"], ["Θ", "\\Theta"], ["Λ", "\\Lambda"], ["Π", "\\Pi"],
      ["Σ", "\\Sigma"], ["Φ", "\\Phi"], ["Ψ", "\\Psi"], ["Ω", "\\Omega"], ["Ξ", "\\Xi"],
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
      ["对齐", "\\begin{aligned} #? &= #? \\\\ #? &= #? \\end{aligned}", "Aligned equations"],
      ["分段", "matrix:cases", "Cases"],
      ["矩阵", "matrix:matrix", "Matrix"],
      ["方括号矩阵", "matrix:bmatrix", "Bracketed matrix"],
      ["行列式", "matrix:vmatrix", "Determinant"],
      ["圆括号矩阵", "matrix:pmatrix", "Parenthesized matrix"],
      ["花括号矩阵", "matrix:Bmatrix", "Braced matrix"],
      ["乘积", "\\prod_{#?}^{#?} #?", "Product"],
      ["二项式", "\\binom{#?}{#?}", "Binomial"],
      ["海森", "\\mathbf{H} = \\begin{bmatrix} \\frac{\\partial^2 f}{\\partial x_i \\partial x_j} \\end{bmatrix}", "Hessian"],
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
      ["⌊ ⌋", "\\left\\lfloor #? \\right\\rfloor", "Floor"],
      ["⌈ ⌉", "\\left\\lceil #? \\right\\rceil", "Ceiling"],
      ["( ]", "\\left( #? \\right]", "Half-open"],
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
      ["零空间", "\\ker(#?)", "Kernel"],
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
      ["理想", "I \\triangleleft R", "Ideal"],
      ["商群", "G / N", "Quotient group"],
      ["置换群", "S_n", "Symmetric group"],
      ["李括号", "[X,Y]", "Lie bracket"],
    ],
  },
  {
    id: "geometry",
    structures: true,
    items: [
      ["角度", "\\theta", "Angle"],
      ["度", "^\\circ", "Degree"],
      ["弧长", "s = \\int \\sqrt{g_{ij}dx^i dx^j}", "Arc length"],
      ["度量张量", "g = g_{ij}\\,dx^i\\otimes dx^j", "Metric tensor"],
      ["克里斯托费尔", "\\Gamma^k_{ij} = \\frac12 g^{kl}\\left(\\partial_i g_{jl}+\\partial_j g_{il}-\\partial_l g_{ij}\\right)", "Christoffel symbols"],
      ["黎曼曲率", "R^i_{jkl} = \\partial_k\\Gamma^i_{jl}-\\partial_l\\Gamma^i_{jk}+\\Gamma^i_{mk}\\Gamma^m_{jl}-\\Gamma^i_{ml}\\Gamma^m_{jk}", "Riemann curvature"],
      ["里奇曲率", "R_{ij} = R^k_{ikj}", "Ricci curvature"],
      ["标量曲率", "R = g^{ij}R_{ij}", "Scalar curvature"],
      ["协变导数", "\\nabla_i V^j = \\partial_i V^j + \\Gamma^j_{ik}V^k", "Covariant derivative"],
      ["李导数", "\\mathcal{L}_X Y = [X,Y]", "Lie derivative"],
      ["外微分", "d\\omega", "Exterior derivative"],
      ["楔积", "\\omega \\wedge \\eta", "Wedge product"],
      ["霍奇星", "\\star \\omega", "Hodge star"],
      ["第一基本形式", "\\mathrm{I} = E\\,du^2 + 2F\\,du\\,dv + G\\,dv^2", "First fundamental form"],
      ["第二基本形式", "\\mathrm{II} = L\\,du^2 + 2M\\,du\\,dv + N\\,dv^2", "Second fundamental form"],
      ["高斯曲率", "K = \\frac{LN-M^2}{EG-F^2}", "Gaussian curvature"],
      ["平均曲率", "H = \\frac{EN+GL-2FM}{2(EG-F^2)}", "Mean curvature"],
      ["测地线", "\\frac{d^2x^i}{dt^2}+\\Gamma^i_{jk}\\frac{dx^j}{dt}\\frac{dx^k}{dt}=0", "Geodesic"],
      ["曲率", "\\kappa = \\frac{|\\mathbf{r}'\\times\\mathbf{r}''|}{|\\mathbf{r}'|^3}", "Curvature"],
      ["挠率", "\\tau = \\frac{(\\mathbf{r}'\\times\\mathbf{r}'')\\cdot\\mathbf{r}'''}{|\\mathbf{r}'\\times\\mathbf{r}''|^2}", "Torsion"],
      ["联络", "\\nabla_X Y", "Connection"],
      ["平行移动", "V^i(t) = V^i(0) - \\int_0^t \\Gamma^i_{jk}\\dot{x}^j V^k dt", "Parallel transport"],
      ["切空间", "T_pM", "Tangent space"],
      ["微分形式", "\\Omega^k(M)", "Differential forms"],
      ["向量场", "X = X^i\\partial_i", "Vector field"],
      ["德拉姆上同调", "H^k_{\\mathrm{dR}}(M)", "de Rham cohomology"],
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
      ["单纯形", "\\Delta^n = \\{(t_0,\\ldots,t_n):\\sum t_i=1\\}", "Simplex"],
      ["复形", "K", "Simplicial complex"],
      ["流形", "M^n", "Manifold"],
      ["豪斯多夫", "T_2 \\text{ space}", "Hausdorff"],
      ["可数", "\\text{countable}", "Countable"],
      ["映射度", "\\deg(f)", "Mapping degree"],
      ["覆叠空间", "p: \\tilde{X} \\to X", "Covering space"],
      ["纤维丛", "F \\to E \\to B", "Fiber bundle"],
      ["悬垂", "\\Sigma X", "Suspension"],
      ["楔和", "X \\vee Y", "Wedge sum"],
      [" smash ", "X \\wedge Y", "Smash product"],
    ],
  },
  {
    id: "relations",
    items: [
      ["=", "="], ["≠", "\\neq"], ["≈", "\\approx"], ["≡", "\\equiv"], ["∼", "\\sim"], ["≅", "\\cong"],
      ["≃", "\\simeq"], ["∝", "\\propto"], ["<", "<"], [">", ">"], ["≤", "\\leq"], ["≥", "\\geq"],
      ["≪", "\\ll"], ["≫", "\\gg"], ["∈", "\\in"], ["∉", "\\notin"], ["∋", "\\ni"], ["⊂", "\\subset"],
      ["⊃", "\\supset"], ["⊆", "\\subseteq"], ["⊇", "\\supseteq"], ["∥", "\\parallel"], ["⊥", "\\perp"],
      ["≺", "\\prec"], ["≻", "\\succ"], ["≼", "\\preceq"], ["≽", "\\succeq"],
      ["≍", "\\asymp"], ["≐", "\\doteq"], ["⊨", "\\models"], ["⊢", "\\vdash"], ["⊣", "\\dashv"],
    ],
  },
  {
    id: "operators",
    items: [
      ["+", "+"], ["−", "-"], ["±", "\\pm"], ["∓", "\\mp"], ["×", "\\times"], ["÷", "\\div"],
      ["·", "\\cdot"], ["∗", "\\ast"], ["∘", "\\circ"], ["∙", "\\bullet"],
      ["∩", "\\cap"], ["∪", "\\cup"], ["∧", "\\wedge"], ["∨", "\\vee"],
      ["⊕", "\\oplus"], ["⊖", "\\ominus"], ["⊗", "\\otimes"], ["⊘", "\\oslash"],
      ["∂", "\\partial"], ["∇", "\\nabla"], ["∞", "\\infty"], ["′", "^{\\prime}"],
      ["∖", "\\setminus"], ["⊓", "\\sqcap"], ["⊔", "\\sqcup"],
      ["†", "\\dagger"], ["‡", "\\ddagger"], ["≀", "\\wr"], ["⋆", "\\star"],
    ],
  },
  {
    id: "bigops",
    items: [
      ["Σ", "\\sum"], ["∫", "\\int"], ["Π", "\\prod"], ["∏", "\\coprod"],
      ["∬", "\\iint"], ["∭", "\\iiint"], ["∮", "\\oint"], ["∯", "\\oiint"], ["∰", "\\oiiint"],
      ["⋂", "\\bigcap"], ["⋃", "\\bigcup"], ["⋀", "\\bigwedge"], ["⋁", "\\bigvee"],
      ["⨁", "\\bigoplus"], ["⨂", "\\bigotimes"], ["⨆", "\\bigsqcup"], ["⨄", "\\biguplus"],
    ],
  },
  {
    id: "arrows",
    items: [
      ["→", "\\rightarrow"], ["←", "\\leftarrow"], ["⇒", "\\Rightarrow"], ["⇐", "\\Leftarrow"],
      ["↔", "\\leftrightarrow"], ["⇔", "\\Leftrightarrow"],
      ["↑", "\\uparrow"], ["↓", "\\downarrow"], ["↦", "\\mapsto"],
      ["⟶", "\\longrightarrow"], ["⟵", "\\longleftarrow"],
      ["⟹", "\\Longrightarrow"], ["⟸", "\\Longleftarrow"], ["⟺", "\\Longleftrightarrow"],
      ["↗", "\\nearrow"], ["↘", "\\searrow"], ["↙", "\\swarrow"], ["↖", "\\nwarrow"],
      ["↪", "\\hookrightarrow"], ["↩", "\\hookleftarrow"],
      ["⇌", "\\rightleftharpoons"], ["⇋", "\\leftrightharpoons"],
      ["↝", "\\leadsto"], ["⇀", "\\rightharpoonup"], ["⇁", "\\rightharpoondown"],
    ],
  },
  {
    id: "sets",
    items: [
      ["∈", "\\in"], ["∉", "\\notin"], ["∅", "\\emptyset"],
      ["∀", "\\forall"], ["∃", "\\exists"], ["∄", "\\nexists"], ["¬", "\\neg"],
      ["∧", "\\land"], ["∨", "\\lor"], ["⟹", "\\implies"], ["⟺", "\\iff"],
      ["∴", "\\therefore"], ["∵", "\\because"],
      ["ℝ", "\\mathbb{R}"], ["ℕ", "\\mathbb{N}"], ["ℤ", "\\mathbb{Z}"], ["ℚ", "\\mathbb{Q}"],
      ["ℂ", "\\mathbb{C}"], ["ℙ", "\\mathbb{P}"], ["ℍ", "\\mathbb{H}"],
      ["⊤", "\\top"], ["⊥", "\\bot"],
    ],
  },
  {
    id: "functions",
    items: [
      ["sin", "\\sin"], ["cos", "\\cos"], ["tan", "\\tan"],
      ["log", "\\log"], ["ln", "\\ln"], ["lg", "\\lg"], ["exp", "\\exp"],
      ["lim", "\\lim"], ["max", "\\max"], ["min", "\\min"], ["sup", "\\sup"], ["inf", "\\inf"],
      ["sin⁻¹", "\\sin^{-1}"], ["cos⁻¹", "\\cos^{-1}"], ["tan⁻¹", "\\tan^{-1}"],
      ["sec", "\\sec"], ["csc", "\\csc"], ["cot", "\\cot"],
      ["arcsin", "\\arcsin"], ["arccos", "\\arccos"], ["arctan", "\\arctan"],
      ["sinh", "\\sinh"], ["cosh", "\\cosh"], ["tanh", "\\tanh"], ["coth", "\\coth"],
      ["det", "\\det"], ["dim", "\\dim"], ["gcd", "\\gcd"], ["lcm", "\\operatorname{lcm}"],
      ["arg", "\\arg"], ["deg", "\\deg"], ["ker", "\\ker"], ["hom", "\\hom"],
      ["Pr", "\\Pr"], ["sgn", "\\operatorname{sgn}"], ["mod", "\\bmod"],
      ["rank", "\\operatorname{rank}"], ["span", "\\operatorname{span}"], ["tr", "\\operatorname{tr}"],
      ["erf", "\\operatorname{erf}"], ["erfc", "\\operatorname{erfc}"],
    ],
  },
  {
    id: "probability",
    structures: true,
    items: [
      ["概率", "\\mathbb{P}(#?)", "Probability"],
      ["期望", "\\mathbb{E}[#?]", "Expectation"],
      ["方差", "\\operatorname{Var}(#?)", "Variance"],
      ["协方差", "\\operatorname{Cov}(#?,#?)", "Covariance"],
      ["正态", "\\mathcal{N}(#?,#?)", "Normal distribution"],
      ["条件", "#? \\mid #?", "Conditional bar"],
      ["独立", "#? \\perp\\!\\!\\!\\perp #?", "Independence"],
      ["贝叶斯", "\\mathbb{P}(A|B) = \\frac{\\mathbb{P}(B|A)\\mathbb{P}(A)}{\\mathbb{P}(B)}", "Bayes theorem"],
      ["二项", "\\operatorname{Bin}(#?,#?)", "Binomial distribution"],
      ["泊松", "\\operatorname{Poisson}(#?)", "Poisson distribution"],
      ["均匀", "\\operatorname{Uniform}(#?,#?)", "Uniform distribution"],
      ["似然", "\\mathcal{L}(#?;#?)", "Likelihood"],
      ["伯努利", "\\operatorname{Bernoulli}(#?)", "Bernoulli distribution"],
      ["卡方", "\\chi^2_{(#?)}", "Chi-squared"],
      ["t 分布", "t_{(#?)}", "Student t"],
      ["F 分布", "F_{(#?,#?)}", "F-distribution"],
      ["伽马", "\\Gamma(#?)", "Gamma distribution"],
      ["贝塔", "\\operatorname{Beta}(#?,#?)", "Beta distribution"],
    ],
  },
  {
    id: "physics",
    structures: true,
    items: [
      ["牛顿第二定律", "\\mathbf{F} = m\\mathbf{a}", "Newton 2nd"],
      ["动能", "E_k = \\frac{1}{2}mv^2", "Kinetic energy"],
      ["动量", "\\mathbf{p} = m\\mathbf{v}", "Momentum"],
      ["万有引力", "F = G\\frac{m_1 m_2}{r^2}", "Gravity"],
      ["功", "W = \\int \\mathbf{F}\\cdot d\\mathbf{r}", "Work"],
      ["欧姆定律", "V = IR", "Ohm law"],
      ["焦耳定律", "P = I^2 R", "Joule heating"],
      ["库仑定律", "F = k_e\\frac{q_1 q_2}{r^2}", "Coulomb law"],
      ["电场", "\\mathbf{E} = \\frac{\\mathbf{F}}{q}", "Electric field"],
      ["高斯定律", "\\oint \\mathbf{E}\\cdot d\\mathbf{A} = \\frac{Q}{\\varepsilon_0}", "Gauss law"],
      ["法拉第定律", "\\mathcal{E} = -\\frac{d\\Phi_B}{dt}", "Faraday law"],
      ["安培定律", "\\oint \\mathbf{B}\\cdot d\\mathbf{l} = \\mu_0 I", "Ampere law"],
      ["洛伦兹力", "\\mathbf{F} = q(\\mathbf{E} + \\mathbf{v}\\times\\mathbf{B})", "Lorentz force"],
      ["麦克斯韦", "\\nabla\\cdot\\mathbf{E}=\\frac{\\rho}{\\varepsilon_0},\\; \\nabla\\cdot\\mathbf{B}=0,\\; \\nabla\\times\\mathbf{E}=-\\frac{\\partial\\mathbf{B}}{\\partial t},\\; \\nabla\\times\\mathbf{B}=\\mu_0\\mathbf{J}+\\mu_0\\varepsilon_0\\frac{\\partial\\mathbf{E}}{\\partial t}", "Maxwell eqns"],
      ["胡克定律", "F = -k x", "Hooke law"],
      ["简谐运动", "x(t) = A\\cos(\\omega t + \\phi)", "SHM"],
      ["理想气体", "PV = nRT", "Ideal gas law"],
      ["热力学第一定律", "\\Delta U = Q - W", "1st law thermo"],
      ["熵", "dS = \\frac{dQ_{\\text{rev}}}{T}", "Entropy"],
      ["玻尔兹曼", "S = k_B \\ln W", "Boltzmann entropy"],
      ["薛定谔方程", "i\\hbar\\frac{\\partial}{\\partial t}\\Psi = \\hat{H}\\Psi", "Schrodinger eqn"],
      ["质能方程", "E = mc^2", "Mass-energy"],
      ["不确定性", "\\Delta x\\,\\Delta p \\geq \\frac{\\hbar}{2}", "Uncertainty"],
      ["光电效应", "E_{\\text{max}} = h\\nu - \\phi", "Photoelectric"],
      ["折射定律", "n_1\\sin\\theta_1 = n_2\\sin\\theta_2", "Snell law"],
      ["多普勒", "f' = f\\frac{c \\pm v_r}{c \\mp v_s}", "Doppler effect"],
      ["黑体辐射", "I(\\nu,T) = \\frac{2h\\nu^3}{c^2}\\frac{1}{e^{h\\nu/k_B T}-1}", "Planck law"],
      ["相对论动量", "E^2 = (pc)^2 + (mc^2)^2", "Energy-momentum"],
      ["德布罗意", "\\lambda = \\frac{h}{p}", "de Broglie"],
      ["杨氏双缝", "d\\sin\\theta = m\\lambda", "Young double-slit"],
    ],
  },
  {
    id: "chemistry",
    structures: true,
    items: [
      ["化学式", "\\ce{ #? }", "Formula"],
      ["反应式", "\\ce{ #? -> #? }", "Reaction"],
      ["可逆", "\\ce{ #? <=> #? }", "Reversible"],
      ["上下箭头", "\\ce{ #? ->[#?][#?] #? }", "Arrow with text"],
      ["H₂O", "\\ce{H2O}", "Water"],
      ["CO₂", "\\ce{CO2}", "Carbon dioxide"],
      ["NaCl", "\\ce{NaCl}", "Sodium chloride"],
      ["H₂SO₄", "\\ce{H2SO4}", "Sulfuric acid"],
      ["NH₃", "\\ce{NH3}", "Ammonia"],
      ["NaOH", "\\ce{NaOH}", "Sodium hydroxide"],
      ["O₂", "\\ce{O2}", "Oxygen"],
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
      ["△", "\\triangle"], ["催化", "\\xrightarrow{\\text{#?}}", "catalyst"],
      ["沉淀", "\\downarrow", "precipitate"], ["气体", "\\uparrow", "gas"],
    ],
  },
  {
    id: "accents",
    items: [
      ["𝐱", "\\mathbf{#?}"], ["ℝ", "\\mathbb{#?}"], ["𝓧", "\\mathcal{#?}"],
      ["x̂", "\\hat{x}"], ["x̄", "\\bar{x}"], ["x̃", "\\tilde{x}"], ["x⃗", "\\vec{x}"],
      ["ẋ", "\\dot{x}"], ["ẍ", "\\ddot{x}"],
      ["x̲", "\\underline{x}"], ["x̅", "\\overline{x}"],
      ["𝑥", "\\mathit{#?}"], ["𝔁", "\\mathfrak{#?}"],
      ["text", "\\text{#?}"], ["rm", "\\mathrm{#?}"],
    ],
  },
  {
    id: "misc",
    items: [
      ["⋯", "\\cdots"], ["…", "\\dots"], ["⋮", "\\vdots"], ["⋱", "\\ddots"],
      ["∞", "\\infty"], ["ℏ", "\\hbar"], ["ℓ", "\\ell"], ["ℜ", "\\Re"], ["ℑ", "\\Im"], ["℘", "\\wp"],
      ["∠", "\\angle"], ["°", "^\\circ"], ["△", "\\triangle"], ["□", "\\Box"], ["◇", "\\Diamond"],
      ["★", "\\bigstar"], ["♮", "\\natural"], ["♭", "\\flat"], ["♯", "\\sharp"],
      ["✓", "\\checkmark"], ["✗", "\\times"], ["§", "\\S"], ["©", "\\copyright"], ["†", "\\dag"],
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
const title = document.getElementById("libraryTitle");
const grid = document.getElementById("symbolGrid");
const searchInput = document.getElementById("symbolSearch");

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

  title.textContent = groupTitle(group);
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
