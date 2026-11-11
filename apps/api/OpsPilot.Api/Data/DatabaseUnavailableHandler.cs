using System.Data.Common;
using Microsoft.AspNetCore.Diagnostics;
using Microsoft.AspNetCore.Mvc;

namespace OpsPilot.Api.Data;

/// <summary>
/// Turns database connectivity failures into 503 problem details instead of an opaque 500, so clients (and the
/// dashboard's error state) can tell "the database is down, try again" from a bug.
/// </summary>
public sealed class DatabaseUnavailableHandler(IProblemDetailsService problems, ILogger<DatabaseUnavailableHandler> logger)
    : IExceptionHandler
{
    public async ValueTask<bool> TryHandleAsync(HttpContext context, Exception exception, CancellationToken ct)
    {
        if (!IsDatabaseFailure(exception)) return false;
        logger.LogWarning("Database unavailable: {Error}", exception.GetBaseException().Message);
        context.Response.StatusCode = StatusCodes.Status503ServiceUnavailable;
        return await problems.TryWriteAsync(new ProblemDetailsContext
        {
            HttpContext = context,
            ProblemDetails = new ProblemDetails
            {
                Status = StatusCodes.Status503ServiceUnavailable,
                Title = "The database is unavailable. Try again shortly.",
            },
            Exception = exception,
        });
    }

    internal static bool IsDatabaseFailure(Exception? e)
    {
        // EF Core wraps connection failures (e.g. InvalidOperationException from the retry strategy).
        for (; e is not null; e = e.InnerException)
        {
            if (e is DbException or TimeoutException) return true;
        }
        return false;
    }
}
