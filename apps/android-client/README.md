# LaTeXSnipper Android Client

`apps/android-client` 是数学工作台移动端项目，技术路线固定为：

- React
- TypeScript
- Vite
- Capacitor

当前已经具备：

- MathLive 编辑器
- Compute Engine 按需加载
- Capacitor 原生剪贴板、分享、文件导入、历史持久化
- Android 原生工程与插件同步

## 目录结构

```text
apps/android-client/
├─ android/                   Android Studio 原生工程
├─ src/
│  ├─ app/                    应用壳、全局布局
│  ├─ features/
│  │  ├─ editor/              MathLive 编辑区
│  │  ├─ compute/             Compute Engine 结果区
│  │  ├─ templates/           快捷模板
│  │  └─ settings/            移动端设置页
│  ├─ services/               剪贴板、文件、分享、存储等服务
│  ├─ styles/                 主题与全局样式
│  ├─ types/                  类型定义
│  ├─ App.tsx
│  └─ main.tsx
├─ capacitor.config.ts
├─ package.json
├─ README.md
└─ vite.config.ts
```

## 开发命令

安装依赖：

```bash
npm install
```

本地开发：

```bash
npm run dev
```

同步到原生工程：

```bash
npm run build
npm run cap:sync
```

打开 Android Studio：

```bash
npm run cap:open:android
```

## Android 发布配置

### 1. 配置包名与应用名

当前 Android 包名：

```text
com.sakuramathcraft.latexsnipper.android
```

当前应用名：

```text
LaTeXSnipper Workbench
```

### 2. 配置签名文件

在 `apps/android-client/android/` 下复制模板：

```bash
copy keystore.properties.example keystore.properties
```

然后填写：

```properties
storeFile=release-keystore.jks
storePassword=你的密码
keyAlias=latexsnipper
keyPassword=你的密码
```

将你的 `release-keystore.jks` 放到 `apps/android-client/android/` 目录。`

如果 `keystore.properties` 存在，`android/app/build.gradle` 会自动使用 release signing；否则会退回 debug signing，便于本地验证。

### 3. 生成发布包

在 Android Studio 中：

- 打开 `Build > Generate Signed Bundle / APK`
- 选择 `Android App Bundle` 或 `APK`
- 选择 `release`

如果想用命令行：

```bash
cd android
.\gradlew bundleRelease
```

APK / AAB 输出目录通常是：

```text
android/app/build/outputs/
```

## 当前原生能力

- 剪贴板：`@capacitor/clipboard`
- 系统分享：`@capacitor/share`
- 文件导入：`@capawesome/capacitor-file-picker`
- 历史持久化：`@capacitor/preferences`