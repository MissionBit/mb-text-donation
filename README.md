# mb-text-donation

## Development

### Open Terminal

1. ```$ git clone https://github.com/MissionBit/mb-text-donation```
2. ```$ cd mb-text-donation```
3. ```$ python3 -m venv venv```
4. ```$ source venv/bin/activate```
5. ```$ pip install -r requirements.txt```
6. Export enviroment variables (or create a [.env file](https://pypi.org/project/python-dotenv/)) including values for ```PUBLISHABLE_KEY```, ```SECRET_KEY```, ```WEBHOOK_SIGNING_SECRET```, ```APPINSIGHTS_INSTRUMENTATIONKEY```, and ```SENDGRID_API_KEY```
7. ```$ FLASK_APP=application.py flask run```

### Test

Navigate to [http://localhost:5000/500](http://localhost:5000/500) to test. replace 500 with any integer value.

Currently, the only automated tests are doctests for the parse_cents module. These can be run with:

```shell
$ python parse_cents.py
…
```

### Coding Standards

For Python we are using the Flask web framework.

In JavaScript and CSS we are currently not using any framework at all.
The application is not yet large enough to justify an asset pipeline.

We should keep an eye on making the front-end compatible with older
browsers, particularly Android phones.

Ideally, our code would be automatically formatted. Here are the tools
I'd recommend:

* Python: [black](https://github.com/ambv/black)
* JavaScript: [prettier](https://prettier.io/)

I would like to have, but don't know the right formatting tools for:

* CSS
* HTML (Jinja2 templates)

We should also consider adding linting (pylint, eslint) or even static type analysis (mypy, flow).

## Runbook

### Deployment

Deployment is currently done manually by pushing a master branch directly to the azure app
service. You can find the git URL and deployment credentials from
[portal.azure.com](https://portal.azure.com), finding the `mb-text-donation` App Service, and
look under the Deployment Center section. A typical workflow might look something like this:

1. Merge PR from github
2. ```$ git pull origin```
3. ```$ git push azure master```

In the future, this should really be automated with CI.
Probably [Azure DevOps](https://dev.azure.com/missionbit/).

We should consider having automated tests and a staging deployment or review
apps, although we wouldn't be much worse off if master was automatically
deployed as-is.

### Canonical Host

The ```CANONICAL_HOST``` environment variable can be used when the app is hosted behind
an Azure Verizon Premium CDN to ensure visitors are redirected to a specific HTTPS url.
In production this is set to `donate.missionbit.com`.

Alternative domains that should not get redirected may also be included, e.g.

```bash
CANONICAL_HOST=donate.missionbit.com gala.missionbit.org
```

### Infrastructure

When a request to <https://donate.missionbit.com/> comes in, it is routed to the
`mb-text-donation-cdn` endpoint (an Azure Verizon Premium CDN), which uses the
`mb-text-donation` App Service as its origin. The DNS for missionbit.com is currently
managed in Cloudflare.

Sendgrid is used to send transactional email. This is managed through the Azure portal.

Stripe is used to process credit card and paymentRequest transactions.

Analytics come from Google Analytics, and events are also sent to the Application Insights
instance `mb-text-donation-insights`. The Application Insights instance is set to do
continuous streaming of data to the `mb-text-donation-insights` container of the
`mbanalyticsstore` storage account.

### Application Insights

To analyze events sent to Application Insights, you can write
[AIQL](https://docs.microsoft.com/en-us/azure/kusto/query/) (Kusto) queries in workbooks.
