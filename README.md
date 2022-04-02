# Freqtrade Cyber Bot Helpers <a href="https://github.com/cyberjunky/freqtrade-cyber-bots/blob/main/README.md#donate"><img src="https://img.shields.io/badge/Donate-PayPal-green.svg" height="40" align="right"></a> 

A collection of Freqtrade bot helpers I wrote. (collection will grow over time)

<img src="images/robots.jpg"></a> 

## Disclaimer
```
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
> My code is [MIT Licensed](LICENSE), read it please.

> Always test your setup and settings with DRY RUNS first!
 
## Freqtrade BotAssistExplorer bot helper named `botassistexplorer.py`
Type = trading pair

### What does it do?

It will fetch the specfied 3C-tools Bot-Assist Top X pairs for your Freqtrade bot to use.

### How does it work?

The data is gathered from the 3c-tools.com website which is sorted on the type of list requested and the pairs between `start-number` and `end-number` are processed. These pairs are not reconstructed but used as they are, after being checked against your optional local Blacklist and the market data on against the used exchange to see if the pairs are valid.

If this is the case the bots config file is updated.
The "pair_whitelist" entry in you config file will be filled with the new pairs.
And the freqtrade get's a reload_config command. (hack for now, until I have rewritten it to a pairlist method)

After this the bot helper will sleep for the set interval time, after which it will repeat these steps.

NOTE: the 'Trading 24h minimal volume' value in your botassistexplorer config can be used to prevent deals with low volume. Random pairs can be excluded using the blacklist. The first top pairs (like BTC and ETH) can also be excluded by increasing the start-number.


NOTE2: I have only tested this with an activated freqtrade python3 enviroment.
You may need in install python packages after activating

```
pip3 install -r requirements.txt
```

You also need to activate the api-server in your freqtrade config file and fill in proper username and password
```
api_server": {
        "enabled": true,
```

### Configuration

This is the layout of the config file used by the `botassistexplorer.py` bot helper:

-   *[settings]*
-   **timezone** - timezone. (default is 'Europe/Amsterdam')
-   **timeinterval** - update timeinterval in Seconds. (default is 86400)
-   **debug** - set to true to enable debug logging to file. (default is False)
-   **logrotate** - number of days to keep logs. (default = 7)
-   **start-number** - start number for the pairs to request (exclude first x). (default is 1)
-   **end-number** - end number for the pairs to request. (default is 200)
-   **list** - the part behind the 'list=' parameter in the url of 3c-tools bot-assist-explorer, you can find it here: https://www.3c-tools.com/markets/bot-assist-explorer
-   **minvolume** - the minimal 24h volume in BTC
-   **notifications** - set to true to enable notifications. (default = False)
-   **notify-urls** - one or a list of apprise notify urls, each in " " seperated with commas. See [Apprise website](https://github.com/caronc/apprise) for more information.


Example: (keys are bogus)
```
[settings]
timezone = Europe/Amsterdam
timeinterval = 3600
debug = False
logrotate = 7
start-number = 1
end-number = 50
list = binance_spot_usdt_highest_volatility_day
ft-config = /home/ron/freqtrade/config.json
minvolume = 50.0
notifications = False
notify-urls = [ "tgram://9995888120:BoJPor6opeHyxx5VVZPX-BoJPor6opeHyxx5VVZPX/" ]
```

## Donate
If you enjoyed this project -and want to support further improvement and development- consider sending a small donation using the PayPal button or one of the Crypto Wallets below. :v:
<a href="https://www.paypal.me/cyberjunkynl/"><img src="https://img.shields.io/badge/Donate-PayPal-green.svg" height="40" align="right"></a>  

Wallets:

- USDT (TRC20): TEQPsmmWbmjTdbufxkJvkbiVHhmL6YWK6R
- USDT (ERC20): 0x73b41c3996315e921cb38d5d1bca13502bd72fe5

- BTC (BTC)   : 18igByUc1W2PVdP7Z6MFm2XeQMCtfVZJw4
- BTC (ERC20) : 0x73b41c3996315e921cb38d5d1bca13502bd72fe5


## Disclamer (Reminder)
```
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
> My code is [MIT Licensed](LICENSE), read it please.

> Always test your settings with DRY RUNS first!
