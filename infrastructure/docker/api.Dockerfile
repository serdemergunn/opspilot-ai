# Build context: repository root (see docker-compose.yml).
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY global.json Directory.Build.props ./
COPY apps/api/OpsPilot.Api/OpsPilot.Api.csproj apps/api/OpsPilot.Api/
RUN dotnet restore apps/api/OpsPilot.Api/OpsPilot.Api.csproj
COPY apps/api/OpsPilot.Api/ apps/api/OpsPilot.Api/
RUN dotnet publish apps/api/OpsPilot.Api/OpsPilot.Api.csproj -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app
COPY --from=build /app .
COPY sample-data/csv /app/seed
ENV ASPNETCORE_URLS=http://+:8080 \
    Seed__CsvDirectory=/app/seed
USER app
EXPOSE 8080
ENTRYPOINT ["dotnet", "OpsPilot.Api.dll"]
