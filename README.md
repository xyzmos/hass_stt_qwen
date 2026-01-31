# Home Assistant 阿里云通义千问 STT 语音识别插件

本插件集成了阿里云通义千问 (Qwen) 实时语音识别服务，为 Home Assistant 提供高精度的语音转文字功能。

## 功能特性

- **模型支持**：支持 `qwen3-asr-flash-realtime`（通义千问实时识别）。
- **图形化配置**：支持通过 Home Assistant 前端界面直接添加集成。
- **多语言支持**：支持中文、英文、粤语等多种语言识别。
- **实时识别**：基于 WebSocket 协议，低延迟实时转写。
- **多区域支持**：支持北京（国内）和新加坡（国际）节点。
- **音频格式**：WAV（PCM 16-bit / 16kHz / 单声道）。

## 安装说明

### 方法一：手动安装

1. 下载本项目代码。
2. 将 `hass_stt_qwen` 文件夹复制到您的 Home Assistant 配置目录下的 `custom_components` 文件夹中。
   - 最终路径应为：`/config/custom_components/hass_stt_qwen/`
3. 重启 Home Assistant。

## 配置指南

1. 登录 Home Assistant。
2. 点击左侧菜单的 **配置** -> **设备与服务**。
3. 点击右下角的 **添加集成** 按钮。
4. 搜索 **阿里通义千问语音识别** 并点击。
5. 在弹出的配置窗口中输入以下信息：
   - **API 密钥**: 您的阿里云 DashScope API 密钥。
     - 获取方式：[阿里云百炼控制台](https://bailian.console.aliyun.com/)
   - **模型**: 选择您需要使用的模型（推荐 `qwen3-asr-flash-realtime`）。
   - **区域**: 根据您的 API Key 所在区域选择（北京或新加坡）。
6. 点击 **提交** 完成配置。

## 使用方法

配置完成后，您可以在 Home Assistant 的语音助手设置中选择 **阿里通义千问语音识别** 作为语音转文字 (STT) 引擎。

1. 进入 **配置** -> **语音助手**。
2. 选择或创建一个语音助手。
3. 在 **语音转文字** 选项中选择 **阿里通义千问语音识别**。

## 常见问题

**Q: 如何获取 API Key？**
A: 请访问 [阿里云百炼控制台](https://bailian.console.aliyun.com/)，开通服务并创建 API Key。

**Q: 插件支持哪些 Home Assistant 版本？**
A: 需要 Home Assistant 支持 SpeechToTextEntity（STT 实体）的版本。

**Q: 支持哪些语言？**
A: 通义千问 Qwen ASR 支持中文、英文、粤语、日语等多种语言。

**Q: 遇到连接失败怎么办？**
A: 请检查 API Key 是否正确，以及网络连接是否正常。如果您在海外，请尝试切换到新加坡区域。

**Q: 如何调整 VAD/超时/接入点？**
A: 在集成的“选项”里可以配置自定义 WebSocket 接入点、是否启用 Server VAD、VAD 参数与超时。

