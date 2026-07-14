class DiscordcliAgents < Formula
  desc "Command-line tool for managing Discord servers and automating Discord via AI agents"
  homepage "https://github.com/1solomonwakhungu/discord-cli"
  url "https://files.pythonhosted.org/packages/source/d/discordcli-agents/discordcli-agents-1.1.0.tar.gz"
  license "MIT"

  depends_on "python@3.12"

  def install
    system "pip3", "install", "--prefix=#{prefix}", "discordcli-agents"
  end

  def caveats
    <<~EOS
      discordcli-agents installs the `discord-cli` command.
      Set your bot token before use:
        export DISCORD_BOT_TOKEN="your-bot-token-here"
    EOS
  end

  test do
    system bin/"discord-cli", "--version"
  end
end
