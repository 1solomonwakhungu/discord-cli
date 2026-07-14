class DiscordcliAgents < Formula
  desc "Command-line tool for managing Discord servers and automating Discord via AI agents"
  homepage "https://github.com/1solomonwakhungu/discord-cli"
  url "https://files.pythonhosted.org/packages/17/41/20e963c8759905290dee3a1890fb59af2172b86cd8cf68aafeca3a12b24a/discordcli_agents-1.2.0.tar.gz"
  sha256 "568e493bf66e3a644d6b47365e60baf7f90e5978c3499fc6b760cfe5725ee52c"
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
