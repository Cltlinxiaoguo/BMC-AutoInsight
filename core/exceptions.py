"""自定义异常."""
class BMCAutoInsightError(Exception):
    """基础异常."""

class ConfigError(BMCAutoInsightError):
    """配置错误."""

class AuthError(BMCAutoInsightError):
    """认证失败."""

class RedfishError(BMCAutoInsightError):
    """Redfish 请求错误."""

class MockFixtureError(BMCAutoInsightError):
    """Mock 数据缺失."""
