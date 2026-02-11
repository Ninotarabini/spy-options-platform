FROM fluent/fluentd-kubernetes-daemonset:v1-debian-elasticsearch

USER root

# Solo instalar plugin Azure
RUN gem install fluent-plugin-azure-loganalytics -v 0.7.0

USER fluent