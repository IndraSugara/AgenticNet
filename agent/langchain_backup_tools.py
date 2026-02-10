"""
LangChain Config Backup Tools

Tools for managing device configuration backups via the agent.
"""
from typing import Optional
from langchain_core.tools import tool

from agent.config_backup import config_backup


@tool
def backup_device_config(
    device_id: str,
    device_name: str,
    config_content: str,
    config_type: str = "running",
    description: str = ""
) -> str:
    """
    Backup a device configuration.
    
    Args:
        device_id: Unique device identifier or IP
        device_name: Device display name
        config_content: The configuration content to backup
        config_type: Type of config (running, startup, custom)
        description: Optional description of this backup
    
    Returns:
        Backup result with version number
    """
    try:
        version = config_backup.backup_config(
            device_id=device_id,
            device_name=device_name,
            config_content=config_content,
            config_type=config_type,
            description=description
        )
        
        return f"""✅ Configuration backed up successfully!

**Device:** {device_name} ({device_id})
**Version:** {version.version}
**Type:** {config_type}
**Size:** {version.size_bytes:,} bytes
**Time:** {version.timestamp[:19]}
"""
    except Exception as e:
        return f"❌ Backup failed: {str(e)}"


@tool
def list_config_versions(device_id: str) -> str:
    """
    List all config backup versions for a device.
    
    Args:
        device_id: Device identifier to list versions for
    
    Returns:
        List of available versions
    """
    try:
        versions = config_backup.get_versions(device_id)
        
        if not versions:
            return f"ℹ️ No backups found for device '{device_id}'."
        
        output = f"## Config Backups for {device_id}\n\n"
        output += f"**Total Versions:** {len(versions)}\n\n"
        
        for v in versions[:10]:  # Show latest 10
            output += f"### Version {v.version}\n"
            output += f"- Time: {v.timestamp[:19]}\n"
            output += f"- Type: {v.config_type}\n"
            output += f"- Size: {v.size_bytes:,} bytes\n"
            if v.description:
                output += f"- Description: {v.description}\n"
            output += "\n"
        
        if len(versions) > 10:
            output += f"_...and {len(versions) - 10} more versions_"
        
        return output
    except Exception as e:
        return f"❌ Error listing versions: {str(e)}"


@tool
def get_config_version(device_id: str, version: int = None) -> str:
    """
    Get a specific config version content.
    
    Args:
        device_id: Device identifier
        version: Version number (default: latest)
    
    Returns:
        Configuration content
    """
    try:
        if version is None:
            config = config_backup.get_latest_version(device_id)
            if not config:
                return f"ℹ️ No backups found for device '{device_id}'."
        else:
            config = config_backup.get_version(device_id, version)
            if not config:
                return f"❌ Version {version} not found for device '{device_id}'."
        
        output = f"## Config - {config.device_name} (v{config.version})\n\n"
        output += f"**Type:** {config.config_type}\n"
        output += f"**Time:** {config.timestamp[:19]}\n"
        output += f"**Size:** {config.size_bytes:,} bytes\n\n"
        output += "```\n"
        # Show first 2000 chars to avoid overflow
        content = config.config_content
        if len(content) > 2000:
            output += content[:2000]
            output += f"\n... (truncated, {len(content) - 2000} more characters)\n"
        else:
            output += content
        output += "\n```"
        
        return output
    except Exception as e:
        return f"❌ Error getting config: {str(e)}"


@tool
def compare_configs(device_id: str, version1: int, version2: int) -> str:
    """
    Compare two configuration versions and show differences.
    
    Args:
        device_id: Device identifier
        version1: First version number
        version2: Second version number
    
    Returns:
        Diff between the two versions
    """
    try:
        result = config_backup.compare_versions(device_id, version1, version2)
        
        if "error" in result:
            return f"❌ {result['error']}"
        
        output = f"## Config Diff: Version {version1} → {version2}\n\n"
        output += f"**Additions:** {result['additions']} lines\n"
        output += f"**Deletions:** {result['deletions']} lines\n"
        output += f"**Total Changes:** {result['total_changes']}\n\n"
        
        if result['total_changes'] == 0:
            output += "✅ No differences found - configurations are identical."
        else:
            output += "```diff\n"
            diff = result['diff']
            if len(diff) > 3000:
                output += diff[:3000]
                output += f"\n... (truncated, showing first 3000 chars)"
            else:
                output += diff
            output += "\n```"
        
        return output
    except Exception as e:
        return f"❌ Error comparing configs: {str(e)}"


@tool
def restore_config(device_id: str, version: int) -> str:
    """
    Get a config version for restore. Note: This returns the config content
    that can be applied to the device manually or via automation.
    
    Args:
        device_id: Device identifier
        version: Version number to restore
    
    Returns:
        Configuration content ready for restore
    """
    try:
        config = config_backup.get_version(device_id, version)
        
        if not config:
            return f"❌ Version {version} not found for device '{device_id}'."
        
        # Create a new backup as "pre-restore" marker
        return f"""## Restore Ready: {config.device_name} (v{version})

**⚠️ Warning:** Review the configuration before applying!

**Device:** {config.device_name}
**Version:** {version}
**Original Time:** {config.timestamp[:19]}
**Config Type:** {config.config_type}

### Configuration Content:
```
{config.config_content[:3000]}{"..." if len(config.config_content) > 3000 else ""}
```

### Next Steps:
1. Copy the configuration above
2. Connect to the device
3. Apply the configuration
4. Verify the changes

_Tip: Create a backup of current config before restoring!_
"""
    except Exception as e:
        return f"❌ Error restoring config: {str(e)}"


@tool
def get_backup_stats() -> str:
    """
    Get statistics about all configuration backups.
    
    Returns:
        Backup statistics summary
    """
    try:
        stats = config_backup.get_backup_stats()
        devices = config_backup.get_all_devices()
        
        output = """## Configuration Backup Statistics

"""
        output += f"**Total Devices:** {stats['total_devices']}\n"
        output += f"**Total Backups:** {stats['total_backups']}\n"
        output += f"**Total Size:** {stats['total_size_mb']:.2f} MB\n"
        
        if stats['last_backup']:
            output += f"**Last Backup:** {stats['last_backup'][:19]}\n"
        
        if devices:
            output += "\n### Devices with Backups:\n"
            for d in devices[:10]:
                output += f"- **{d['device_name']}** ({d['device_id']}): "
                output += f"{d['version_count']} versions\n"
        
        return output
    except Exception as e:
        return f"❌ Error getting stats: {str(e)}"


@tool
def delete_config_version(device_id: str, version: int) -> str:
    """
    Delete a specific config backup version.
    
    Args:
        device_id: Device identifier
        version: Version number to delete
    
    Returns:
        Deletion result
    """
    try:
        if config_backup.delete_version(device_id, version):
            return f"✅ Deleted version {version} for device '{device_id}'."
        else:
            return f"❌ Version {version} not found for device '{device_id}'."
    except Exception as e:
        return f"❌ Error deleting version: {str(e)}"


def get_backup_tools() -> list:
    """Get all config backup tools"""
    return [
        backup_device_config,
        list_config_versions,
        get_config_version,
        compare_configs,
        restore_config,
        get_backup_stats,
        delete_config_version,
    ]
